"""跟进展示：金额精度、缺失与超收、终态、通知时间选择及列表/详情一致性。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from backend.modules.task.dao import notification_dao
from backend.modules.task.dto.task_dto import TaskListQuery
from backend.modules.task.entity import notifications
from backend.modules.task.policy.followup_policy import amounts, waiting
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from sqlalchemy import insert


def line(expected, received="0", status="open"):
    return {
        "expected_amount": Decimal(expected) if expected is not None else None,
        "received_amount": Decimal(received),
        "status": status,
    }


def test_decimal_amounts_do_not_net_over_receipt_against_other_lines():
    outstanding, percent, bar = amounts([line("100", "150"), line("100", "20")])
    assert (outstanding, percent, bar) == (Decimal("80"), Decimal("85"), Decimal("85"))
    assert amounts([line("0.3", "0.1")]) == (Decimal("0.2"), Decimal("33.3"), Decimal("33.3"))
    assert amounts([line("100", "120")]) == (Decimal("0"), Decimal("120"), Decimal("100"))
    assert amounts([line("100", "80", "received")]) == (Decimal("0"), Decimal("80"), Decimal("80"))
    assert amounts([line("100", "20", "superseded")])[0] == 0


@pytest.mark.parametrize("lines", [[], [line(None)], [line("100", "20"), line(None)]])
def test_unknown_amounts_are_not_shown_as_zero_or_partial_total(lines):
    assert amounts(lines) == (None, None, None)


@pytest.mark.parametrize("expected", ["0", "-1"])
def test_nonpositive_base_has_no_percentage(expected):
    assert amounts([line(expected)])[1:] == (None, None)


def test_waiting_counts_complete_days_and_stops_at_terminal_status():
    now = datetime(2026, 10, 19, 8, tzinfo=UTC)
    task = {
        "status": "awaiting_invoice",
        "created_at": (now - timedelta(days=2, hours=23)).replace(tzinfo=None),
    }
    assert waiting(task, now) == "已等待 2 天"
    assert waiting({**task, "created_at": now + timedelta(days=1)}, now) == "已等待 0 天"
    assert waiting({**task, "status": "completed"}, now) == "已完成"
    assert waiting({**task, "status": "superseded"}, now) == "已被替代"


def test_list_and_detail_use_latest_actual_sent_time(engine, app_services, approved):
    service = app_services["tasks"]
    initial = service.browse(TaskListQuery()).groups[0].tasks[0]
    assert Decimal(initial.outstandingAmount) == Decimal("120.5")
    assert initial.receiptPercent == "0" and initial.lastContactAt is None
    assert initial.followupEmployee == "" and initial.waitingLabel == "已等待 0 天"
    task_id = approved["id"]
    now = datetime(2026, 10, 19, 8)
    with engine.begin() as connection:
        for version, status, sent_at, employee in (
            (1, "sent", now, "最近发送员工"),
            (2, "sent", now - timedelta(days=1), "补录旧发送员工"),
            (3, "draft", None, "草稿员工"),
            (4, "failed", now + timedelta(hours=1), "失败员工"),
        ):
            connection.execute(
                insert(notifications).values(
                    task_id=task_id,
                    version=version,
                    content="隔离测试通知",
                    created_by="user:test",
                    sender_name=employee,
                    status=status,
                    sent_at=sent_at,
                    created_at=now,
                    updated_at=now,
                )
            )
        assert notification_dao.latest_sent_by_tasks(connection, []) == {}
    listed = service.browse(TaskListQuery()).groups[0].tasks[0]
    detail = service.detail(task_id).task
    assert listed.lastContactAt == detail.lastContactAt == "2026-10-19T08:00:00+00:00"
    assert listed.followupEmployee == detail.followupEmployee == "最近发送员工"
    assert listed.outstandingAmount == detail.outstandingAmount
