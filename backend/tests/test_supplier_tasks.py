"""供应商跨报关单合并：真实服务与隔离数据库/文件，企微使用假适配器。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from backend.app import create_app
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.modules.task.dao import notification_dao, supplier_task_dao
from backend.modules.task.dto.delivery_dto import (
    DeliveryPreviewRequest,
    DeliveryRefreshRequest,
    DeliverySubmitRequest,
)
from backend.modules.task.dto.notification_dto import NotificationBatchRecord
from backend.modules.task.dto.supplier_group_dto import GroupSave
from backend.modules.task.dto.supplier_task_dto import SupplierNotificationDraft, SupplierNotificationRecord
from backend.modules.task.dto.task_dto import TaskBoardQuery
from backend.modules.task.entity import documents, task_lines
from backend.modules.task.entity import tasks as task_table
from backend.modules.task.service.delivery_receipt_service import DeliveryReceiptService
from backend.modules.task.service.delivery_submit_service import DeliverySubmitService
from backend.modules.task.service.supplier_notification_service import SupplierNotificationService
from backend.modules.task.service.supplier_task_service import SupplierTaskService
from backend.modules.task.service.task_board_service import TaskBoardService
from backend.tests.delivery_fixtures import Channel
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_task import USER, FakeWecom, approve, draft, prepare_all
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError


@pytest.fixture
def grouped(ns, engine, app_services):
    save(
        ns, engine, bundle([purchase("200", "870"), purchase("201", "871")], [customs("870"), customs("871")])
    )
    approve(app_services, "CD870")
    approve(app_services, "CD871")
    tasks = rows(engine, "SELECT * FROM task_tasks ORDER BY id")
    groups = SupplierTaskService(app_services["tasks"])
    return tasks, groups, SupplierNotificationService(groups)


def archive(app_services, tasks):
    for task in tasks:
        prepare_all(app_services, task["id"])
    app_services["groups"].save(
        GroupSave(supplierId=str(tasks[0]["supplier_id"]), chatId="wr001", revision=0, enabled=True), USER
    )


def body(groups, anchor):
    detail = groups.detail(anchor)
    return SupplierNotificationDraft(
        revision=detail.notification.revision,
        groupName="上海供应商开票群",
        employee="张三",
        message=detail.notification.message,
        scopeRevision=detail.scopeRevision,
        requestId=uuid4(),
    )


def test_board_groups_before_paging_and_expands_matching_declaration(grouped, engine, app_services):
    tasks, groups, _ = grouped
    board = TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])
    merged = board.browse(TaskBoardQuery(groupBy="supplier", pageSize=1, recordNo="CD870"))
    assert merged.total == merged.openTotal == 1
    assert len(merged.items) == 1 and merged.items[0].grouped
    assert merged.items[0].taskIds == [str(task["id"]) for task in tasks]
    assert merged.items[0].task.orderNumbers == ["SUB-200", "SUB-201"]
    assert "CD871" in merged.items[0].task.recordNumber
    assert merged.items[0].task.declarationNumber == "REAL870、REAL871"
    assert merged.items[0].task.expectedAmount == "241.0"
    assert board.browse(TaskBoardQuery(groupBy="declaration")).total == 2
    detail = groups.detail(tasks[0]["id"])
    assert len(detail.memberTasks) == 2 and len(detail.documents) == 2 and len(detail.lines) == 4
    assert {member.declarationNumber for member in detail.memberTasks} == {"REAL870", "REAL871"}
    assert {row.recordNumber for row in detail.reviewRows} == {"CD870", "CD871"}
    assert all(
        row.orderCount == 1 and row.customsStatusLabel == row.financeStatusLabel == "已通过"
        for row in detail.reviewRows
    )
    assert detail.preparation.contractCount == detail.preparation.signedPendingCount == 2
    assert detail.preparation.archivedCount == 0 and not detail.preparation.contractsReady
    assert len(detail.declarationRows) == 2 and detail.preparation.declarationCount == 2
    assert all(
        row.customs.taskId == row.taskId and row.invoice.recordNumber == row.recordNumber
        for row in detail.declarationRows
    )
    assert len(detail.declarationDocuments) == 6
    assert {doc.taskId for doc in detail.documents} == {str(task["id"]) for task in tasks}
    assert {doc.recordNumber for doc in detail.declarationDocuments} == {"CD870", "CD871"}
    assert "SUB-201" in detail.notification.defaultMessage and "CD871" in detail.notification.defaultMessage


def test_save_scope_preserves_ledgers_and_is_idempotent(grouped, engine, app_services):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    review = rows(engine, "SELECT * FROM review_records")
    lines = rows(engine, "SELECT * FROM task_lines")
    request = body(groups, tasks[0]["id"])
    saved = notifications.save_draft(tasks[0]["id"], request, USER)
    notifications.save_draft(tasks[0]["id"], request, USER)
    assert len(rows(engine, "SELECT * FROM task_notifications")) == 2
    assert len(rows(engine, "SELECT * FROM task_events WHERE event_type='supplier_notice_scope'")) == 1
    assert rows(engine, "SELECT * FROM review_records") == review
    assert rows(engine, "SELECT * FROM task_lines") == lines
    assert len(saved.notification.attachments) == 2
    assert saved.preparation.contractSummary == "2 / 2 已归档" and saved.preparation.contractsReady
    assert {doc.recordNumber for doc in saved.documents} == {"CD870", "CD871"}
    assert {event.recordNumber for event in saved.notification.history} == {"CD870", "CD871"}
    assert saved.notification.record.allowed
    board = TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])
    assert not board.browse(TaskBoardQuery(groupBy="supplier")).items[0].notifyRecord.allowed
    assert board.browse(TaskBoardQuery(groupBy="supplier")).items[0].notifyTargets == []
    with pytest.raises(ApiError, match="合并"):
        app_services["notifications"].save_draft(tasks[1]["id"], draft(revision=1), USER)


@pytest.mark.parametrize(
    "states,archived",
    [
        (("pending", "pending"), 0),
        (("ready", "pending"), 1),
        (("ready", "failed"), 1),
        (("ready", "ready"), 2),
    ],
)
def test_notification_lists_all_contract_states_and_reports_actual_readiness(
    grouped, engine, app_services, states, archived
):
    tasks, groups, _ = grouped
    for task, state in zip(tasks, states, strict=True):
        if state == "pending":
            continue  # 尚无合同记录时也应按子采购单生成待保存项。
        prepare_all(app_services, task["id"])
        if state == "failed":
            with engine.begin() as connection:
                connection.execute(
                    update(documents)
                    .where(documents.c.task_id == task["id"])
                    .values(status="failed", archive_path=None, error_message="共享盘不可写")
                )
    detail = groups.detail(tasks[0]["id"])
    assert [doc.orderNumber for doc in detail.notificationDocuments] == ["SUB-200", "SUB-201"]
    assert [doc.status for doc in detail.notificationDocuments] == list(states)
    assert {doc.taskId for doc in detail.notificationDocuments} == {str(task["id"]) for task in tasks}
    assert len(detail.notification.attachments) == archived
    assert f"子采购合同已归档 {archived} / 2 份" in detail.notification.scopeReason
    assert "附带全部对应" not in detail.notification.scopeReason
    if archived < 2:
        assert "合同尚未齐全，请先完成归档" in detail.notification.scopeReason
        assert "全部对应子采购合同已归档" not in detail.notification.scopeReason
    else:
        assert "全部对应子采购合同已归档，发送时请附上" in detail.notification.scopeReason
    if "failed" in states:
        assert detail.notificationDocuments[1].error == "共享盘不可写"


def test_group_manual_record_commits_all_members_and_replays(grouped, engine, app_services):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    saved = notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    request = SupplierNotificationRecord(
        revision=saved.notification.revision,
        scopeRevision=saved.scopeRevision,
        sentAt=datetime.now(UTC),
        note="已线下统一通知供应商",
        confirmed=True,
    )
    notifications.record(tasks[0]["id"], request, USER)
    events = rows(engine, "SELECT * FROM task_events")
    notifications.record(tasks[0]["id"], request, USER)
    assert rows(engine, "SELECT * FROM task_events") == events
    assert {task["status"] for task in rows(engine, "SELECT * FROM task_tasks")} == {"awaiting_invoice"}
    assert {notice["status"] for notice in rows(engine, "SELECT * FROM task_notifications")} == {"sent"}


def test_scope_change_refuses_stale_draft(grouped, engine, app_services):
    tasks, groups, notifications = grouped
    old = body(groups, tasks[0]["id"])
    prepare_all(app_services, tasks[1]["id"])
    with pytest.raises(ApiError, match="范围已变化"):
        notifications.save_draft(tasks[0]["id"], old, USER)
    assert not rows(engine, "SELECT * FROM task_notifications")


@pytest.mark.parametrize("unknown", [False, True])
def test_merged_wecom_includes_every_contract_and_protects_all_members(
    grouped, engine, app_services, unknown
):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    settings = Settings(wecom_send_enabled=True, subpo_archive_root=app_services["tasks"].archive.root)
    app_services["tasks"].settings = settings
    notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    channel = Channel()
    if unknown:
        channel.create_error = ApiError(502, "结果未知")
    submit = DeliverySubmitService(engine, settings, channel, app_services["tasks"])
    preview = submit.preview(tasks[0]["id"], DeliveryPreviewRequest(revision=1, groupRevision=1), USER)
    assert preview.orderNumbers == ["SUB-200", "SUB-201"] and len(preview.files) == 2
    request = DeliverySubmitRequest(
        revision=1, groupRevision=1, snapshotSha256=preview.snapshotSha256, requestId=uuid4().hex
    )
    result = submit.submit(tasks[0]["id"], request, USER)
    assert len(channel.uploads) == 2 and len(channel.creates) == 1
    assert submit.submit(tasks[0]["id"], request, USER).id == result.id
    with pytest.raises(ApiError, match="未决"):
        app_services["notifications"].save_draft(tasks[1]["id"], draft(revision=1), USER)
    assert all(task["status"] == "notify_pending" for task in rows(engine, "SELECT * FROM task_tasks"))
    if unknown:
        assert result.status == "unknown"
        with pytest.raises(ApiError, match="未决"):
            notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    else:
        channel.success()
        receipt = DeliveryReceiptService(engine, channel)
        receipt.refresh(tasks[0]["id"], DeliveryRefreshRequest(deliveryId=result.id), USER)
        assert all(task["status"] == "awaiting_invoice" for task in rows(engine, "SELECT * FROM task_tasks"))
        assert all(
            notice["channel"] == "wecom" and notice["status"] == "sent"
            for notice in rows(engine, "SELECT * FROM task_notifications")
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("ns_account", "other"),
        ("supplier_id", 78),
        ("company_id", 99),
        ("currency", "USD"),
        ("supplier_id", None),
    ],
)
def test_identity_boundaries_are_never_merged(grouped, engine, app_services, field, value):
    tasks, _, _ = grouped
    with engine.begin() as connection:
        connection.execute(update(task_table).where(task_table.c.id == tasks[1]["id"]).values({field: value}))
    board = TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])
    result = board.browse(TaskBoardQuery(groupBy="supplier"))
    assert result.total == 2
    assert all(len(item.taskIds) == 1 for item in result.items)


def test_completed_anchor_keeps_open_siblings_and_supports_history(grouped, engine):
    tasks, _, _ = grouped
    with engine.begin() as connection:
        connection.execute(
            update(task_table).where(task_table.c.id == tasks[0]["id"]).values(status="completed")
        )
    with engine.connect() as connection:
        assert [row["id"] for row in supplier_task_dao.by_anchor(connection, tasks[0]["id"])] == [
            tasks[1]["id"]
        ]
        assert [
            row["id"] for row in supplier_task_dao.by_anchor(connection, tasks[0]["id"], completed=True)
        ] == [tasks[0]["id"]]


def test_already_notified_members_remain_visible_but_are_excluded_from_new_notice(
    grouped, engine, app_services
):
    from backend.modules.task.dto.notification_dto import NotificationRecord

    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    app_services["notifications"].save_draft(tasks[0]["id"], draft(), USER)
    app_services["notifications"].record(
        tasks[0]["id"],
        NotificationRecord(revision=1, sentAt=datetime.now(UTC), confirmed=True, note="已通知第一张"),
        USER,
    )
    saved = notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    assert len(saved.memberTasks) == len(saved.documents) == 2
    assert saved.notification.taskIds == [str(tasks[1]["id"])]
    assert len(saved.notification.attachments) == 1
    assert [doc.orderNumber for doc in saved.notificationDocuments] == ["SUB-201"]
    assert "子采购合同已归档 1 / 1 份" in saved.notification.scopeReason
    assert "SUB-201" in saved.notification.message and "SUB-200" not in saved.notification.message
    notifications.record(
        tasks[0]["id"],
        SupplierNotificationRecord(
            revision=saved.notification.revision,
            scopeRevision=saved.scopeRevision,
            sentAt=datetime.now(UTC),
            confirmed=True,
            note="只通知新任务",
        ),
        USER,
    )
    assert {row["status"] for row in rows(engine, "SELECT * FROM task_notifications")} == {"sent"}


def test_board_batch_records_only_eligible_members_and_preserves_sent_notice(grouped, engine, app_services):
    tasks, _, _ = grouped
    archive(app_services, tasks)
    first, second = tasks
    notifications = app_services["notifications"]
    notifications.record_batch(NotificationBatchRecord(taskIds=[str(first["id"])]), USER)
    prior = rows(engine, f"SELECT * FROM task_notifications WHERE task_id={first['id']}")
    board = TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])
    item = board.browse(TaskBoardQuery(groupBy="supplier")).items[0]
    assert item.taskIds == [str(first["id"]), str(second["id"])]
    assert item.currentNode == "notification" and item.notifyRecord.allowed
    assert len(item.notifyTargets) == 1
    target = item.notifyTargets[0]
    assert target.id == str(second["id"])
    assert target.recordNumber == "CD871" and target.orderNumbers == ["SUB-201"]
    assert target.supplier == item.task.supplier
    separate = board.browse(TaskBoardQuery(groupBy="declaration"))
    assert [target.id for value in separate.items for target in value.notifyTargets] == [target.id]

    result = notifications.record_batch(
        NotificationBatchRecord(taskIds=[target.id for target in item.notifyTargets]), USER
    )
    assert [value.id for value in result.recorded] == [str(second["id"])]
    assert not result.skipped
    assert rows(engine, f"SELECT * FROM task_notifications WHERE task_id={first['id']}") == prior
    done = board.browse(TaskBoardQuery(groupBy="supplier")).items[0]
    assert not done.notifyRecord.allowed and done.notifyTargets == []

    # 页面读取后任务可能已被其他操作登记；提交仍复核，不能创建第二份通知。
    before = rows(engine, "SELECT * FROM task_notifications ORDER BY id")
    stale = notifications.record_batch(NotificationBatchRecord(taskIds=[target.id]), USER)
    assert not stale.recorded and len(stale.skipped) == 1
    assert "无需重复登记" in stale.skipped[0].reason
    assert rows(engine, "SELECT * FROM task_notifications ORDER BY id") == before


def test_board_batch_targets_exclude_members_without_archived_contracts(grouped, engine, app_services):
    tasks, _, _ = grouped
    board = TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])
    blocked = board.browse(TaskBoardQuery(groupBy="supplier")).items[0]
    assert not blocked.notifyRecord.allowed and blocked.notifyTargets == []
    prepare_all(app_services, tasks[1]["id"])
    item = board.browse(TaskBoardQuery(groupBy="supplier")).items[0]
    assert item.notifyRecord.allowed
    assert [target.id for target in item.notifyTargets] == [str(tasks[1]["id"])]


def test_manual_record_rolls_back_all_members_on_database_failure(grouped, engine, app_services, monkeypatch):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    saved = notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    original = notification_dao.mark_sent
    calls = []

    def fail_second(*args):
        calls.append(True)
        if len(calls) == 2:
            raise SQLAlchemyError("测试事务回滚")
        return original(*args)

    monkeypatch.setattr(notification_dao, "mark_sent", fail_second)
    request = SupplierNotificationRecord(
        revision=saved.notification.revision,
        scopeRevision=saved.scopeRevision,
        sentAt=datetime.now(UTC),
        confirmed=True,
        note="统一通知",
    )
    with pytest.raises(ApiError, match="不会重复登记"):
        notifications.record(tasks[0]["id"], request, USER)
    assert {row["status"] for row in rows(engine, "SELECT * FROM task_notifications")} == {"draft"}
    assert {row["status"] for row in rows(engine, "SELECT * FROM task_tasks")} == {"notify_pending"}


def test_http_supplier_routes_require_session_and_preserve_scope(grouped, context, ns, engine):
    tasks, _, _ = grouped
    app = create_app(context.settings, ns, engine, wecom=FakeWecom())
    anchor = tasks[0]["id"]
    path = f"/api/task/supplier-tasks/{anchor}"
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        headers = {"Origin": context.settings.origin}
        assert (
            client.post(
                "/api/session",
                headers=headers,
                json={"username": "admin", "password": context.settings.admin_password},
            ).status_code
            == 200
        )
        response = client.get(path)
        assert response.status_code == 200 and len(response.json()["memberTasks"]) == 2
        detail = response.json()
        request = {
            "revision": 0,
            "groupName": "开票群",
            "employee": "张三",
            "message": detail["notification"]["message"],
            "scopeRevision": detail["scopeRevision"],
            "requestId": str(uuid4()),
        }
        saved = client.post(path + "/notification/draft", headers=headers, json=request)
        assert saved.status_code == 200 and len(saved.json()["notification"]["taskIds"]) == 2
        assert client.get("/api/task/supplier-tasks/0").status_code == 400


def test_new_pending_member_invalidates_saved_send_scope(grouped, ns, engine, app_services):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    saved = notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    save(ns, engine, bundle([purchase("202", "872")], [customs("872")]))
    approve(app_services, "CD872")
    settings = Settings(wecom_send_enabled=True, subpo_archive_root=app_services["tasks"].archive.root)
    submit = DeliverySubmitService(engine, settings, Channel(), app_services["tasks"])
    with pytest.raises(ApiError, match="待通知任务范围已变化"):
        submit.preview(tasks[0]["id"], DeliveryPreviewRequest(revision=1, groupRevision=1), USER)
    with pytest.raises(ApiError, match="待通知任务范围已变化"):
        notifications.record(
            tasks[0]["id"],
            SupplierNotificationRecord(
                revision=saved.notification.revision,
                scopeRevision=groups.detail(tasks[0]["id"]).scopeRevision,
                sentAt=datetime.now(UTC),
                confirmed=True,
                note="旧范围登记",
            ),
            USER,
        )


def test_non_root_basis_change_during_upload_prevents_channel_create(grouped, ns, engine, app_services):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    settings = Settings(wecom_send_enabled=True, subpo_archive_root=app_services["tasks"].archive.root)
    channel = Channel()
    submit = DeliverySubmitService(engine, settings, channel, app_services["tasks"])
    preview = submit.preview(tasks[0]["id"], DeliveryPreviewRequest(revision=1, groupRevision=1), USER)

    def invalidate():
        save(
            ns,
            engine,
            bundle(
                [purchase("200", "870"), purchase("201", "871", amounts=("99.00", "20.00"))],
                [customs("870"), customs("871")],
            ),
        )

    channel.after_upload = invalidate
    result = submit.submit(
        tasks[0]["id"],
        DeliverySubmitRequest(
            revision=1, groupRevision=1, snapshotSha256=preview.snapshotSha256, requestId=uuid4().hex
        ),
        USER,
    )
    assert result.status == "failed" and not channel.creates
    assert {row["status"] for row in rows(engine, "SELECT * FROM task_notifications")} == {"draft"}


@pytest.mark.parametrize("received,status,percent", [("150", "partial", "62.2"), ("0", "received", "0")])
def test_group_amounts_preserve_actual_receipts_and_line_closure_rules(
    grouped, engine, app_services, received, status, percent
):
    from decimal import Decimal

    tasks, groups, _ = grouped
    with engine.begin() as connection:
        connection.execute(
            update(task_lines)
            .where(task_lines.c.task_id == tasks[0]["id"], task_lines.c.expected_amount > 100)
            .values(received_amount=Decimal(received), status=status)
        )
    board = TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])
    summary = board.browse(TaskBoardQuery(groupBy="supplier")).items[0].task
    detail = groups.detail(tasks[0]["id"]).task
    assert summary.receiptPercent == detail.receiptPercent == percent
    assert Decimal(summary.receivedAmount) == Decimal(detail.receivedAmount) == Decimal(received)
    assert Decimal(summary.outstandingAmount) == Decimal(detail.outstandingAmount) == Decimal("140.5")
