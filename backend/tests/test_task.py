"""task 模块：审核通过生成任务、重新审核替代、列表与详情、合同归档、通知登记、供应商群、HTTP。

来源经 source 真实保存，审核经 review 真实确认（SQLite 隔离库，合成 NS 数据）；NS 合同与企微用假实现。
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.core.events import EventBus
from backend.integrations.contract_archive import ContractArchive
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.public import ApprovedLine, ReviewApproved
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService, SourceDirectory
from backend.modules.task.dto.notification_dto import NotificationDraft, NotificationRecord
from backend.modules.task.dto.supplier_group_dto import GroupQuery, GroupSave
from backend.modules.task.dto.task_dto import TaskListQuery
from backend.modules.task.policy.task_policy import group_key
from backend.modules.task.service.document_service import DocumentService
from backend.modules.task.service.notification_service import NotificationService
from backend.modules.task.service.supplier_group_service import SupplierGroupService
from backend.modules.task.service.task_generation_service import on_review_approved
from backend.modules.task.service.task_service import TaskService
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from fastapi.testclient import TestClient

USER = "user:admin"


class FakeContracts:
    environment = "prod"

    def __init__(self):
        self.calls = []
        self.content = b"%PDF-1.4 contract"

    def unavailable_reason(self):
        return ""

    def download(self, number, supplier, declaration):
        self.calls.append((number, supplier, declaration))
        return {
            "ns_id": "501",
            "environment": "prod",
            "filename": "subpo-contract-501.pdf",
            "content": self.content,
        }


class FakeWecom:
    def group(self, chat_id):
        return {"groupName": "上海供应商开票群", "chatId": chat_id, "employee": "张三", "userid": "zhangsan"}

    def groups(self, *, refresh=False):
        item = {**self.group("wr001"), "memberCount": 3, "createdAt": 1_700_000_000}
        return {"items": [item], "unavailableCount": 0}


@pytest.fixture
def app_services(engine, tmp_path):
    events = EventBus()
    events.subscribe(ReviewApproved, on_review_approved)
    directory = SourceDirectory(engine)
    contracts = FakeContracts()
    tasks = TaskService(engine, directory, contracts, ContractArchive(tmp_path / "share"))
    (tmp_path / "share").mkdir()
    return {
        "review": ReviewService(engine, DeclarationService(engine), events),
        "tasks": tasks,
        "documents": DocumentService(engine, directory, contracts, tasks.archive, tasks),
        "notifications": NotificationService(engine, tasks),
        "groups": SupplierGroupService(engine, directory, FakeWecom()),
        "contracts": contracts,
    }


def approve(services, record_no, note=""):
    result = services["review"].browse(DeclarationListQuery())
    item = next(group for group in result.groups if group.recordNumber == record_no)
    services["review"].approve(
        int(item.id), ApproveRequest(contentSha256=item.contentSha256, note=note), USER
    )


def task_rows(engine):
    return rows(engine, "SELECT * FROM task_tasks ORDER BY id")


@pytest.fixture
def approved(ns, engine, app_services):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(app_services, "CD870")
    return task_rows(engine)[0]


def test_approval_generates_task_with_frozen_lines(engine, approved):
    assert approved["status"] == "documents_pending" and approved["review_revision"] == 1
    assert approved["record_no"] == "CD870" and approved["supplier_id"] and approved["company_id"]
    lines = rows(engine, "SELECT * FROM task_lines ORDER BY purchase_line_id")
    assert [(r["status"], r["unit"], Decimal(str(r["expected_amount"]))) for r in lines] == [
        ("open", "个", Decimal("100.5")),
        ("open", "个", Decimal("20")),
    ]
    events = rows(engine, "SELECT * FROM task_events")
    assert [(e["from_status"], e["to_status"], e["actor"]) for e in events] == [
        (None, "documents_pending", USER)
    ]


def test_reapproval_supersedes_open_task_and_regenerates(ns, engine, app_services, approved):
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    approve(app_services, "CD870", "金额更正")
    tasks = task_rows(engine)
    assert [(t["status"], t["review_revision"]) for t in tasks] == [
        ("superseded", 1),
        ("documents_pending", 2),
    ]
    lines = rows(engine, "SELECT task_id, status, expected_amount FROM task_lines ORDER BY id")
    assert [line["status"] for line in lines] == ["superseded", "superseded", "open", "open"]
    assert Decimal(str(lines[2]["expected_amount"])) == Decimal("99")


def test_completed_task_lines_stay_active_and_are_skipped(ns, engine, app_services, approved):
    # 收票完成由发票比对驱动（第 4d 步），此处直接置为已完成以验证"只生成一次"。
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE task_tasks SET status = 'completed'")
        connection.exec_driver_sql("UPDATE task_lines SET status = 'received'")
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    approve(app_services, "CD870")
    assert [t["status"] for t in task_rows(engine)] == ["completed"]


def line(review_line_id, purchase_line_id, order_id, supplier_id=7, company_id=3, currency="CNY"):
    return ApprovedLine(
        review_line_id=review_line_id,
        purchase_order_id=order_id,
        purchase_line_id=purchase_line_id,
        supplier_id=supplier_id,
        company_id=company_id,
        order_no=f"SUB-{order_id}",
        currency=currency,
        quantity=Decimal("1"),
        unit="个",
        amount=Decimal("10"),
    )


def event(review_id, lines, superseded=None):
    return ReviewApproved(
        review_id=review_id,
        superseded_review_id=superseded,
        ns_account="prod",
        customs_declaration_id=review_id,
        record_no=f"CD{review_id}",
        revision=1,
        approved_by=USER,
        lines=lines,
    )


def test_grouping_by_supplier_company_currency_and_isolation(engine):
    lines = [
        line(1, 11, 1),
        line(2, 12, 2),  # 同供应商、公司、币种的另一张子采购单：合并到同一任务
        line(3, 13, 3, currency="USD"),  # 币种不同：单独任务
        line(4, 14, 4, supplier_id=None),  # 供应商身份缺失：按子采购单隔离
        line(5, 15, 5, supplier_id=None),
    ]
    with engine.begin() as connection:
        on_review_approved(connection, event(1, lines))
        on_review_approved(connection, event(2, [line(6, 11, 1), line(7, 16, 6)]))  # 11 已有有效任务行
    counts = rows(engine, "SELECT task_id, COUNT(*) AS n FROM task_lines GROUP BY task_id ORDER BY task_id")
    assert [row["n"] for row in counts] == [2, 1, 1, 1, 1]
    assert group_key(None, 3, "CNY", 4) != group_key(None, 3, "CNY", 5)
    assert group_key(7, 3, "CNY", 1) == group_key(7, 3, "CNY", 2)


def test_failing_generation_rolls_back_review(ns, engine, app_services):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE task_events")
    with pytest.raises(ApiError):
        approve(app_services, "CD870")
    assert rows(engine, "SELECT id FROM review_records") == []


def test_list_groups_search_and_counts(ns, engine, app_services, approved):
    tasks = app_services["tasks"]
    by_supplier = tasks.browse(TaskListQuery())
    assert by_supplier.total == 1 and by_supplier.counts.needsAttention == 1
    group = by_supplier.groups[0]
    assert group.label == "上海 供应商（有限）公司" and group.tasks[0].orderNumbers == ["SUB-200"]
    assert group.tasks[0].expectedAmount == "120.5" and group.counts.completed == 0
    by_declaration = tasks.browse(TaskListQuery(groupBy="declaration"))
    assert by_declaration.groups[0].label == "CD870"
    for keyword in ("CD870", "SUB-200", "上海"):
        assert tasks.browse(TaskListQuery(keyword=keyword)).total == 1
    assert tasks.browse(TaskListQuery(keyword="不存在")).total == 0
    assert tasks.browse(TaskListQuery(status="superseded")).total == 0


def test_detail_documents_notification_and_steps(app_services, approved):
    detail = app_services["tasks"].detail(approved["id"])
    assert detail.task.statusLabel == "待保存子采购合同" and detail.sourceStatus == "current"
    assert [doc.orderNumber for doc in detail.documents] == ["SUB-200"] and detail.documents[
        0
    ].prepare.allowed
    assert "SUB-200" in detail.notification.message and not detail.notification.record.allowed
    assert [step.state for step in detail.steps][:3] == ["done", "current", "waiting"]
    assert [line.quantity for line in detail.lines] == ["10", "10"]
    assert detail.events[0].label == "财务审核通过，生成开票任务"


def prepare_all(services, task_id):
    detail = services["tasks"].detail(task_id)
    for doc in detail.documents:
        detail = services["documents"].prepare(task_id, int(doc.orderId), USER)
    return detail


def test_prepare_archives_contract_and_advances_task(engine, app_services, approved, tmp_path):
    detail = prepare_all(app_services, approved["id"])
    assert detail.task.status == "notify_pending" and detail.documents[0].status == "ready"
    saved = rows(engine, "SELECT * FROM task_documents")[0]
    assert saved["status"] == "archived" and saved["sha256"] and saved["archive_path"].endswith(".pdf")
    assert list((tmp_path / "share").rglob("*.pdf"))
    again = app_services["documents"].prepare(approved["id"], int(detail.documents[0].orderId), USER)
    assert again.task.status == "notify_pending" and len(app_services["contracts"].calls) == 1


def test_prepare_rejects_changed_contract_and_service_identity(engine, app_services, approved):
    services, task_id = app_services, approved["id"]
    order_id = int(services["tasks"].detail(task_id).documents[0].orderId)
    with pytest.raises(ApiError) as error:
        services["documents"].prepare(task_id, order_id, "service:bot")
    assert error.value.status == 403
    archive = services["documents"].archive
    services["documents"].archive = None
    with pytest.raises(ApiError, match="共享盘"):
        services["documents"].prepare(task_id, order_id, USER)
    services["documents"].archive = archive
    # 先登记首次获取记录但共享盘失败，再次获取到不同内容时拒绝覆盖。
    save_fail = archive.save
    archive.save = lambda *args: (_ for _ in ()).throw(ApiError(503, "共享盘保存失败"))
    with pytest.raises(ApiError, match="共享盘保存失败"):
        services["documents"].prepare(task_id, order_id, USER)
    assert rows(engine, "SELECT status FROM task_documents")[0]["status"] == "failed"
    archive.save = save_fail
    services["contracts"].content = b"%PDF-1.4 changed"
    with pytest.raises(ApiError, match="首次获取记录不同"):
        services["documents"].prepare(task_id, order_id, USER)


def draft(revision=0, group="上海供应商开票群", employee="张三", message="请开票"):
    return NotificationDraft(revision=revision, groupName=group, employee=employee, message=message)


def record(revision=1, sent_at=None, note="已发送"):
    sent = sent_at or datetime.now(UTC)
    return NotificationRecord(revision=revision, sentAt=sent, note=note, confirmed=True)


def test_notification_versions_and_manual_record(engine, app_services, approved):
    services, task_id = app_services, approved["id"]
    notes = services["notifications"]
    assert notes.save_draft(task_id, draft(), USER).notification.revision == 1
    with pytest.raises(ApiError, match="已被修改"):
        notes.save_draft(task_id, draft(revision=0), USER)
    with pytest.raises(ApiError, match="共享盘"):
        notes.record(task_id, record(), USER)
    prepare_all(services, task_id)
    with pytest.raises(ApiError, match="发送时间"):
        notes.record(task_id, record(sent_at=datetime.now(UTC) + timedelta(days=1)), USER)
    sent = record()
    detail = notes.record(task_id, sent, USER)
    assert detail.task.status == "awaiting_invoice" and detail.notification.statusLabel == "人工登记已发送"
    assert detail.notification.history[0].attachments and not detail.notification.edit.allowed
    assert notes.record(task_id, sent, USER).task.status == "awaiting_invoice"  # 重试返回原结果
    with pytest.raises(ApiError, match="不可重复登记"):
        notes.record(task_id, record(note="另一次"), USER)
    with pytest.raises(ApiError, match="只读"):
        notes.save_draft(task_id, draft(revision=1), USER)
    statuses = [e["to_status"] for e in rows(engine, "SELECT to_status FROM task_events ORDER BY id")]
    assert statuses == ["documents_pending", "notify_pending", "awaiting_invoice"]


def test_superseded_task_is_read_only(ns, engine, app_services, approved):
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    approve(app_services, "CD870")
    detail = app_services["tasks"].detail(approved["id"])
    assert detail.sourceStatus == "superseded" and not detail.prepare.allowed
    assert not detail.notification.edit.allowed
    with pytest.raises(ApiError, match="替代"):
        app_services["notifications"].save_draft(approved["id"], draft(), USER)


def test_supplier_group_save_and_prefill(engine, app_services, approved):
    groups = app_services["groups"]
    supplier = groups.supplier_options(GroupQuery()).items[0]
    saved = groups.save(GroupSave(chatId="wr001", supplierId=supplier.supplierId, revision=0), USER)
    assert (saved.groupName, saved.employee, saved.revision) == ("上海供应商开票群", "张三", 1)
    with pytest.raises(ApiError, match="已被修改"):
        groups.save(GroupSave(chatId="wr001", supplierId=supplier.supplierId, revision=0), USER)
    disabled = groups.save(
        GroupSave(chatId="wr001", supplierId=supplier.supplierId, revision=1, enabled=False), USER
    )
    assert not disabled.enabled and disabled.revision == 2
    groups.save(GroupSave(chatId="wr001", supplierId=supplier.supplierId, revision=2), USER)
    assert groups.browse(GroupQuery(keyword="上海"), USER).total == 1
    notification = app_services["tasks"].detail(approved["id"]).notification
    assert notification.supplierGroup and notification.groupName == "上海供应商开票群"
    with pytest.raises(ApiError) as error:
        groups.save(GroupSave(chatId="wr001", supplierId="999999", revision=0), USER)
    assert error.value.status == 404


def test_http_task_routes(context, ns, engine, tmp_path):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    app = create_app(context.settings, context.ns, context.engine, business_engine=engine, wecom=FakeWecom())
    with TestClient(app) as client:
        assert client.post("/api/tasks/query", json={}).status_code == 401
        headers = {"Origin": context.settings.origin}
        login = client.post(
            "/api/session",
            headers=headers,
            json={"username": "admin", "password": context.settings.admin_password},
        )
        assert login.status_code == 200
        item = client.post("/api/review/declarations/query", json={}, headers=headers).json()["groups"][0]
        approved = client.post(
            f"/api/review/declarations/{item['id']}/approve",
            json={"contentSha256": item["contentSha256"]},
            headers=headers,
        )
        assert approved.status_code == 200
        listed = client.post("/api/tasks/query", json={"groupBy": "declaration"}, headers=headers)
        assert listed.status_code == 200 and listed.json()["total"] == 1
        task_id = listed.json()["groups"][0]["tasks"][0]["id"]
        detail = client.get(f"/api/tasks/{task_id}", headers=headers)
        assert detail.status_code == 200 and detail.json()["task"]["status"] == "documents_pending"
        assert client.get("/api/tasks/0", headers=headers).status_code == 400
        assert client.get("/api/tasks/999", headers=headers).status_code == 404
        groups = client.post("/api/tasks/supplier-groups/query", json={}, headers=headers)
        assert groups.status_code == 200 and groups.json()["manage"]["allowed"]
