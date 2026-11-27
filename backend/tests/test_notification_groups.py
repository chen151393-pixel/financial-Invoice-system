"""按组登记：超过 50 条、整组回滚、范围变更、旧合并通知保护与 HTTP。"""

import pytest
from backend.core.errors import ApiError
from backend.modules.review.dto.review_dto import ApproveRequest
from backend.modules.task.dto.notification_group_dto import NotificationGroupBatchRecord
from backend.modules.task.dto.task_dto import TaskBoardQuery
from backend.modules.task.service import notification_batch_service
from backend.modules.task.service.task_board_service import TaskBoardService
from backend.tests.review_helpers import approve_customs
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_supplier_tasks import archive, body
from backend.tests.test_supplier_tasks import grouped as grouped
from backend.tests.test_task import USER, approve, draft, prepare_all
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError


def request(board, group_by="supplier"):
    return NotificationGroupBatchRecord(
        groupBy=group_by,
        groups=[{"id": item.task.id, "scopeRevision": item.notifyScopeRevision} for item in board.items],
    )


def browse(engine, services, group_by="supplier"):
    return TaskBoardService(engine, services["tasks"].directory, services["tasks"]).browse(
        TaskBoardQuery(groupBy=group_by)
    )


def test_group_larger_than_50_records_every_member_without_client_task_ids(grouped, engine, ns, app_services):
    tasks, _, _ = grouped
    additions = [purchase(str(202 + i), str(872 + i)) for i in range(49)]
    save(ns, engine, bundle(additions, [customs(str(872 + i)) for i in range(49)]))
    for i in range(49):
        declaration = rows(
            engine,
            "SELECT id, content_sha256 FROM source_customs_declarations WHERE record_no=:number",
            number=f"CD{872 + i}",
        )[0]
        approve_customs(app_services["review"], declaration["id"])
        app_services["review"].approve(
            declaration["id"], ApproveRequest(contentSha256=declaration["content_sha256"]), USER
        )
    tasks = rows(engine, "SELECT * FROM task_tasks ORDER BY id")
    assert len(tasks) == 51
    for task in tasks:
        prepare_all(app_services, task["id"])
    board = browse(engine, app_services)
    assert len(board.items) == 1 and len(board.items[0].notifyTargets) == 51
    selection = request(board)
    assert "taskIds" not in selection.model_dump()
    result = app_services["notifications"].record_groups(selection, USER)
    assert result.recordedGroups == 1 and result.recordedTasks == 51
    assert result.skippedGroups == result.unknownGroups == 0
    assert result.groups[0].taskIds == [str(task["id"]) for task in tasks]
    before = rows(engine, "SELECT * FROM task_notifications ORDER BY id")
    replay = app_services["notifications"].record_groups(selection, USER)
    assert replay.recordedTasks == 0 and replay.skippedGroups == 1
    assert rows(engine, "SELECT * FROM task_notifications ORDER BY id") == before


@pytest.mark.parametrize("failure", ["business", "database"])
def test_group_rolls_back_all_members_and_other_groups_continue(
    grouped, engine, ns, app_services, monkeypatch, failure
):
    tasks, _, _ = grouped
    other = purchase("202", "872")
    other[1]["custrecord_swc_subpo_vendor"] = {"id": "88", "refName": "另一供应商"}
    save(ns, engine, bundle([other], [customs("872")]))
    approve(app_services, "CD872")
    all_tasks = rows(engine, "SELECT * FROM task_tasks ORDER BY id")
    for task in all_tasks:
        prepare_all(app_services, task["id"])
    selection = request(browse(engine, app_services))
    original = notification_batch_service.change_status

    def fail_second(connection, task, *args):
        if task["id"] == tasks[1]["id"]:
            if failure == "business":
                raise ApiError(409, "隔离测试：组内第二个任务不可登记")
            raise SQLAlchemyError("isolated group failure")
        return original(connection, task, *args)

    monkeypatch.setattr(notification_batch_service, "change_status", fail_second)
    result = app_services["notifications"].record_groups(selection, USER)
    assert result.recordedGroups == 1 and result.recordedTasks == 1
    assert result.unknownGroups == (failure == "database")
    assert result.skippedGroups == (failure == "business")
    assert [item.status for item in result.groups] == [
        "unknown" if failure == "database" else "skipped",
        "recorded",
    ]
    notices = rows(engine, "SELECT * FROM task_notifications")
    assert [value["task_id"] for value in notices] == [all_tasks[-1]["id"]]
    statuses = rows(engine, "SELECT status FROM task_tasks ORDER BY id")
    assert [value["status"] for value in statuses] == ["notify_pending", "notify_pending", "awaiting_invoice"]


@pytest.mark.parametrize("change", ["member", "draft"])
def test_new_member_or_new_draft_skips_whole_group(grouped, engine, ns, app_services, change):
    tasks, _, _ = grouped
    archive(app_services, tasks)
    selection = request(browse(engine, app_services))
    if change == "member":
        save(ns, engine, bundle([purchase("202", "872")], [customs("872")]))
        approve(app_services, "CD872")
    else:
        app_services["notifications"].save_draft(tasks[0]["id"], draft(), USER)
    before = rows(engine, "SELECT * FROM task_notifications")
    result = app_services["notifications"].record_groups(selection, USER)
    assert result.skippedGroups == 1 and result.recordedTasks == 0
    assert "范围已变化" in result.groups[0].reason
    assert rows(engine, "SELECT * FROM task_notifications") == before


def test_group_expansion_excludes_already_notified_member(grouped, engine, app_services):
    from backend.modules.task.dto.notification_dto import NotificationBatchRecord

    tasks, _, _ = grouped
    archive(app_services, tasks)
    app_services["notifications"].record_batch(NotificationBatchRecord(taskIds=[str(tasks[0]["id"])]), USER)
    before = rows(engine, "SELECT * FROM task_notifications")
    result = app_services["notifications"].record_groups(request(browse(engine, app_services)), USER)
    assert result.recordedGroups == result.recordedTasks == 1
    assert result.groups[0].taskIds == [str(tasks[1]["id"])]
    assert rows(engine, "SELECT * FROM task_notifications ORDER BY id")[0] == before[0]


def test_group_http_contract(grouped, engine, app_services):
    import asyncio

    import httpx
    from backend.core.dependencies import current_owner
    from backend.core.middleware import register_error_handlers
    from backend.modules.task.controller.task_controller import create_router
    from fastapi import FastAPI

    tasks, _, _ = grouped
    archive(app_services, tasks)
    app = FastAPI()
    app.dependency_overrides[current_owner] = lambda: USER
    register_error_handlers(app)
    app.include_router(create_router(app_services["tasks"], None, app_services["notifications"], None, None))

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = "/api/tasks/notification/record-groups"
            payload = request(browse(engine, app_services)).model_dump(mode="json")
            invalid = await client.post(path, json={**payload, "taskIds": ["1"]})
            assert invalid.status_code == 400
            result = await client.post(path, json=payload)
            assert result.status_code == 200
            assert result.json()["recordedGroups"] == 1 and result.json()["recordedTasks"] == 2

    asyncio.run(check())


def test_saved_merged_notice_cannot_be_split_through_declaration_groups(grouped, engine, app_services):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    stale = request(browse(engine, app_services, "declaration"), "declaration")
    notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    result = app_services["notifications"].record_groups(stale, USER)
    assert result.skippedGroups == 2 and result.recordedTasks == 0
    assert {row["status"] for row in rows(engine, "SELECT * FROM task_notifications")} == {"draft"}


def test_group_request_rejects_invalid_scope_and_service_actor(grouped, engine, app_services):
    selection = request(browse(engine, app_services))
    with pytest.raises(ApiError, match="服务身份只读"):
        app_services["notifications"].record_groups(selection, "service:test")
    for groups in ([], selection.model_dump()["groups"] * 2):
        with pytest.raises(ValidationError):
            NotificationGroupBatchRecord(groupBy="supplier", groups=groups)
    with pytest.raises(ValidationError):
        NotificationGroupBatchRecord(**selection.model_dump(), taskIds=["1"])
