"""应收看板：财务审核月份、回收期限、金额、采购员、真实审核链路及页面授权。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.modules.identity.policy.api_page_policy import required_pages
from backend.modules.review.public import review_approval_times
from backend.modules.task.dto.notification_dto import NotificationBatchRecord
from backend.modules.task.dto.recovery_dto import RecoveryQuery
from backend.modules.task.policy import recovery_policy as policy
from backend.modules.task.service.recovery_service import RecoveryService, current_owners
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_task import USER, approve, prepare_all, task_rows
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

TODAY = date(2026, 11, 9)


def row(task_id, month="2026-10", *, supplier=1, company=3, member="5", status="awaiting_invoice", **values):
    approved_day = date(int(month[:4]), int(month[5:]), 19)
    expected = values.pop("expected", Decimal("100"))
    received = values.pop("received", Decimal("0"))
    return {
        "id": task_id,
        "supplier_id": supplier,
        "supplier": values.pop("name", f"供应商{supplier}"),
        "company_id": company,
        "company": "绎视",
        "member_key": member,
        "member_name": "纪琴" if member != "none" else "",
        "record_no": values.pop("record_no", f"CD{task_id}"),
        "orders": values.pop("orders", [f"POE{task_id}"]),
        "expected": expected,
        "received": received,
        "outstanding": values.pop(
            "outstanding", None if expected is None else max(Decimal(0), expected - received)
        ),
        "status": status,
        "node": "invoices",
        "node_label": "待供应商开票",
        "approved_on": approved_day,
        "month": month,
        "due": policy.due_date(month),
        "collected": policy.collected(status),
        **values,
    }


def test_month_due_date_and_default_cohort():
    assert policy.due_date("2026-10") == date(2026, 11, 30)
    assert policy.due_date("2026-12") == date(2027, 1, 31)
    assert policy.due_date("2027-01") == date(2027, 2, 28)
    assert policy.default_month(TODAY) == "2026-11"
    assert policy.default_month(date(2027, 1, 3)) == "2027-01"
    assert policy.window(date(2027, 2, 1)) == ["2026-11", "2026-12", "2027-01", "2027-02"]
    # 只有发票全部收齐才算收回；部分收票不算
    assert [policy.collected(s) for s in ("partially_received", "documents_incomplete", "completed")] == [
        False,
        True,
        True,
    ]


def test_cards_split_amounts_and_keep_unknown_out_of_totals():
    rows = [
        row(1, status="completed", expected=Decimal("300")),
        row(2, status="partially_received", expected=Decimal("200"), received=Decimal("50")),
        row(3, expected=None, supplier=2),
    ]
    overdue = [row(9, "2026-09", expected=Decimal("80"))]
    cards = policy.cards(rows, overdue, "2026-10", TODAY)
    assert cards["due"] == {"tasks": 3, "suppliers": 2, "amount": "500.00", "unknown": 1}
    assert cards["collected"]["tasks"] == 1 and cards["collected"]["amount"] == "350.00"
    assert cards["collected"]["rate"] == 33.3
    assert cards["outstanding"]["tasks"] == 2 and cards["outstanding"]["amount"] == "150.00"
    assert cards["outstanding"]["unknown"] == 1 and cards["outstanding"]["daysLeft"] == 21
    assert cards["overdue"]["tasks"] == 1 and cards["overdue"]["months"] == ["9月"]
    assert cards["overdue"]["longOverdue"] == 0


def test_months_states_and_recent_rate():
    rows = [row(1, "2026-08", status="completed"), row(2, "2026-08"), row(3, "2026-10"), row(4, "2026-11")]
    months, recent = policy.months(rows, TODAY)
    assert [(m["label"], m["state"], m["tasks"], m["rate"]) for m in months] == [
        ("8月", "closed", 2, 50.0),
        ("9月", "closed", 0, None),
        ("10月", "due", 1, 0.0),
        ("11月", "open", 1, 0.0),
    ]
    # 平均不含本月通知、尚在回收期的月份
    assert recent == 33.3


def test_buyers_concentration_and_groups():
    rows = [
        row(1, supplier=1, member="5", expected=Decimal("50")),
        row(2, supplier=1, member="5", expected=Decimal("70")),
        row(3, supplier=2, member="none", expected=Decimal("400")),
        row(4, supplier=3, member="6", status="completed"),
    ]
    rows[3]["member_name"] = "王静"
    buyers = policy.buyers(rows)
    assert [(b["name"], b["tasks"], b["outstanding"], b["rate"]) for b in buyers] == [
        ("王静", 1, 0, 100.0),
        ("纪琴", 2, 2, 0.0),
        ("未指定", 1, 1, 0.0),
    ]
    share = policy.concentration(rows)
    assert share["amount"] == "520.00" and share["suppliers"] == 2
    assert [(item["name"], item["share"]) for item in share["top"]] == [("供应商2", 76.9), ("供应商1", 23.1)]
    groups = policy.groups([r for r in rows if not r["collected"]], "outstanding", TODAY)
    assert [(g["supplierName"], g["tasks"], g["amount"], g["memberName"]) for g in groups] == [
        ("供应商2", 1, "400.00", "未指定"),
        ("供应商1", 2, "120.00", "纪琴"),
    ]
    assert [item["taskId"] for item in groups[1]["items"]] == ["2", "1"]
    assert groups[0]["daysLeft"] == 21 and groups[0]["approvedOn"] == "2026-10-19"


def test_board_filters_views_and_pagination():
    rows = [
        row(1, "2026-11", supplier=1, name="任丘科迈", orders=["POE20260807003"]),
        row(2, "2026-11", supplier=2, name="永康帅标", member="none"),
        row(3, "2026-09", supplier=3, name="泉州贺稳"),
        row(4, "2026-11", supplier=4, name="诸暨华毅", status="completed", company=4),
    ]
    board = RecoveryService.board(rows, RecoveryQuery(), TODAY)
    assert board.month == "2026-11" and board.dueDate == "2026-12-31" and board.monthLabel == "11月开票"
    assert board.cards.due.tasks == 3 and board.cards.outstanding.tasks == 2
    assert board.cards.overdue.tasks == 1 and board.list.summary.tasks == 2
    assert [o.id for o in board.options.buyers] == ["5", "none"]
    assert board.options.months[0].name == "11月"
    every = RecoveryService.board(rows, RecoveryQuery(month="all", view="due"), TODAY)
    assert every.dueDate is None and every.cards.due.tasks == 4 and every.list.total == 4
    overdue = RecoveryService.board(rows, RecoveryQuery(view="overdue"), TODAY)
    assert [g.supplierName for g in overdue.list.items] == ["泉州贺稳"]
    assert overdue.list.items[0].daysLeft == -9
    assert RecoveryService.board(rows, RecoveryQuery(memberId="none"), TODAY).cards.due.tasks == 1
    assert RecoveryService.board(rows, RecoveryQuery(companyId="4", view="collected"), TODAY).list.total == 1
    found = RecoveryService.board(rows, RecoveryQuery(supplierName="科迈，帅标"), TODAY)
    assert found.cards.due.tasks == 2
    assert RecoveryService.board(rows, RecoveryQuery(orderNo="0807"), TODAY).cards.due.tasks == 1
    assert RecoveryService.board(rows, RecoveryQuery(orderNo="cd2"), TODAY).cards.due.tasks == 1
    paged = RecoveryService.board(rows, RecoveryQuery(month="all", view="due", pageSize=3, page=2), TODAY)
    assert paged.list.pages == 2 and len(paged.list.items) == 1


@pytest.mark.parametrize(
    ("now", "today", "month"),
    [
        (datetime(2026, 11, 27, 4, tzinfo=UTC), "2026-11-27", "2026-11"),
        (datetime(2026, 11, 30, 15, 59, 59, tzinfo=UTC), "2026-11-30", "2026-11"),
        (datetime(2026, 11, 30, 16, tzinfo=UTC), "2026-12-01", "2026-12"),
        (datetime(2026, 12, 31, 15, 59, 59, tzinfo=UTC), "2026-12-31", "2026-12"),
        (datetime(2026, 12, 31, 16, tzinfo=UTC), "2027-01-01", "2027-01"),
    ],
)
def test_default_month_follows_beijing_month_even_without_data(engine, now, today, month):
    board = RecoveryService(engine).browse(RecoveryQuery(), now)
    assert board.today == today
    assert board.month == board.defaultMonth == month
    assert board.dueDate == policy.due_date(month).isoformat()
    assert board.cards.due.tasks == 0 and board.list.total == 0


def test_default_does_not_fall_back_to_history_or_override_explicit_month():
    rows = [row(1)]
    current = RecoveryService.board(rows, RecoveryQuery(), TODAY)
    assert current.month == current.defaultMonth == "2026-11"
    assert current.cards.due.tasks == 0
    historical = RecoveryService.board(rows, RecoveryQuery(month="2026-10"), TODAY)
    assert historical.month == "2026-10" and historical.defaultMonth == "2026-11"
    assert historical.cards.due.tasks == 1
    every = RecoveryService.board(rows, RecoveryQuery(month="all"), TODAY)
    assert every.month == "all" and every.cards.due.tasks == 1


def test_query_validation():
    for values in ({"month": "2026-13"}, {"memberId": "abc"}, {"view": "fake"}, {"pageSize": 51}):
        with pytest.raises(ValidationError):
            RecoveryQuery(**values)
    assert RecoveryQuery(month="all", memberId="none").month == "all"


def test_current_owner_ignores_future_versions():
    records = [
        {
            "supplier_id": 1,
            "company_id": 3,
            "member_id": 5,
            "member_name": "纪琴",
            "effective_date": date(2026, 1, 1),
        },
        {"supplier_id": 1, "company_id": 3, "member_id": 6, "member_name": "王静", "effective_date": TODAY},
        {
            "supplier_id": 1,
            "company_id": 3,
            "member_id": 7,
            "member_name": "朱新卫",
            "effective_date": date(2027, 1, 1),
        },
    ]
    assert current_owners(records, TODAY)[(1, 3)]["member_name"] == "王静"


def notify(services, task_id, day):
    body = NotificationBatchRecord(taskIds=[str(task_id)], notifiedOn=day)
    assert services["notifications"].record_batch(body, USER).recorded


def test_real_task_enters_cohort_on_finance_approval_without_notification(engine, app_services, approved):
    task_id = approved["id"]
    service = RecoveryService(engine)
    now = datetime(2026, 11, 27, 4, tzinfo=UTC)
    today = date(2026, 11, 27)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE task_tasks SET created_at=:created WHERE id=:id"),
            {"created": datetime(2026, 10, 20), "id": task_id},
        )
        connection.execute(
            text("UPDATE review_records SET approved_at=:approved WHERE id=:id"),
            {"approved": datetime(2026, 10, 19, 2), "id": approved["review_id"]},
        )
        connection.execute(
            text(
                "INSERT INTO task_supplier_owners (supplier_id, company_id, member_id, member_name, "
                "effective_date, reason, actor, created_at) VALUES (:s, :c, 9, '纪琴', :d, '分工', 'test', :n)"
            ),
            {
                "s": approved["supplier_id"],
                "c": approved["company_id"],
                "d": today - timedelta(days=30),
                "n": now.replace(tzinfo=None),
            },
        )
    month = "2026-10"
    # 合同尚未归档、没有通知记录，也按财务审核日期进入开票月份；读取不改变流程事实。
    pending = service.browse(RecoveryQuery(month=month, view="due"), now)
    assert pending.cards.due.tasks == 1 and pending.cards.outstanding.tasks == 1
    assert pending.list.items[0].items[0].node == "documents"
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM task_notifications")).scalar() == 0
        assert connection.execute(text("SELECT status FROM task_tasks")).scalar() == "documents_pending"
    prepare_all(app_services, task_id)
    notify(app_services, task_id, today - timedelta(days=1))
    # 11月才通知不挪动10月财务审核的月份，也不重复计数。
    assert service.browse(RecoveryQuery(month="2026-11"), now).cards.due.tasks == 0
    board = service.browse(RecoveryQuery(month=month, view="due"), now)
    assert board.cards.due.tasks == 1 and board.cards.due.amount == "120.50"
    assert board.cards.outstanding.amount == "120.50" and board.cards.overdue.tasks == 0
    group = board.list.items[0]
    assert group.approvedOn == group.items[0].approvedOn == "2026-10-19"
    assert group.notifiedOn == group.approvedOn  # 旧客户端的一版本日期别名。
    assert group.memberName == "纪琴" and group.items[0].recordNo == "CD870"
    assert group.items[0].nodeLabel == "待供应商开票" and group.dueDate == policy.due_date(month).isoformat()
    assert [b.name for b in board.buyers] == ["纪琴"] and board.options.buyers[0].id == "9"
    # 到期后仍未收齐即逾期，月份不变
    later = datetime.combine(policy.due_date(month) + timedelta(days=2), datetime.min.time(), UTC)
    assert service.browse(RecoveryQuery(view="overdue"), later).cards.overdue.tasks == 1
    with engine.begin() as connection:
        connection.execute(text("UPDATE task_tasks SET status='completed' WHERE id=:id"), {"id": task_id})
    done = service.browse(RecoveryQuery(month=month, view="collected"), later)
    assert done.cards.collected.tasks == 1 and done.cards.collected.rate == 100.0
    assert done.cards.overdue.tasks == 0 and done.list.total == 1
    exported = service.export(RecoveryQuery(month=month, view="collected", pageSize=1), later)
    lines = exported.content.lstrip("\ufeff").splitlines()
    assert exported.count == 1 and lines[0].startswith("开票月份,供应商") and "CD870" in lines[1]
    assert "财务审核通过日期" in lines[0] and "2026-10-19" in lines[1]
    assert exported.filename == f"invoice-recovery-{month}-collected.csv"


@pytest.mark.parametrize(
    ("approved_at", "month", "day"),
    [
        (datetime(2026, 10, 31, 15, 59, 59), "2026-10", "2026-10-31"),
        (datetime(2026, 10, 31, 16), "2026-11", "2026-11-01"),
    ],
)
def test_approval_month_uses_china_date_not_task_generation_date(engine, approved, approved_at, month, day):
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_records SET approved_at=:time WHERE id=:id"),
            {"time": approved_at, "id": approved["review_id"]},
        )
        # 双审核后放行可能晚于财务审核，不能按任务创建时间误归到12月。
        connection.execute(text("UPDATE task_tasks SET created_at=:time"), {"time": datetime(2026, 12, 2)})
    board = RecoveryService(engine).browse(
        RecoveryQuery(month=month, view="due"), datetime(2026, 12, 15, tzinfo=UTC)
    )
    assert board.cards.due.tasks == 1
    assert board.list.items[0].items[0].approvedOn == day


def test_reapproval_counts_only_successor_in_its_finance_approval_month(ns, engine, app_services, approved):
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_records SET approved_at=:time WHERE id=:id"),
            {"time": datetime(2026, 10, 19), "id": approved["review_id"]},
        )
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    approve(app_services, "CD870", "金额更正")
    old, new = task_rows(engine)
    assert old["status"] == "superseded"
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_records SET approved_at=:time WHERE id=:id"),
            {"time": datetime(2026, 11, 2), "id": new["review_id"]},
        )
        times = review_approval_times(connection, [old["review_id"], new["review_id"]])
        assert times[old["review_id"]] == datetime(2026, 10, 19)
        assert times[new["review_id"]] == datetime(2026, 11, 2)
    service = RecoveryService(engine)
    now = datetime(2026, 11, 27, tzinfo=UTC)
    assert service.browse(RecoveryQuery(month="2026-10"), now).cards.due.tasks == 0
    current = service.browse(RecoveryQuery(month="all", view="due"), now)
    assert current.cards.due.tasks == 1 and current.cards.due.amount == "119.00"
    assert current.list.items[0].items[0].approvedOn == "2026-11-02"


def test_missing_approval_date_cannot_fall_back_to_task_creation(engine, approved, monkeypatch):
    monkeypatch.setattr("backend.modules.task.service.recovery_service.review_approval_times", lambda *_: {})
    with pytest.raises(ApiError, match="缺少财务审核通过记录"):
        RecoveryService(engine).browse(RecoveryQuery(month="all"))


def test_http_route_and_page_permission(engine, env):
    assert required_pages("POST", "/api/task/recovery/query") == ("invoice-recovery",)
    app = create_app(load_settings(env), engine=engine)
    with TestClient(app) as client:
        auth = {"Authorization": "Bearer " + env["SERVICE_API_KEY"]}
        assert client.post("/api/task/recovery/query", json={}).status_code == 401
        assert client.post("/api/task/recovery/query", json={"month": "x"}, headers=auth).status_code == 400
        result = client.post("/api/task/recovery/query", json={}, headers=auth)
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["cards"]["due"]["tasks"] == 0 and len(body["months"]) == 4 and body["list"]["items"] == []
        exported = client.post("/api/task/recovery/export", json={"view": "due"}, headers=auth)
        assert exported.status_code == 200 and exported.json()["count"] == 0
