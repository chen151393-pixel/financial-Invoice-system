"""查询回归：限制重复查库，并验证分页只装载本页完整数据且保留通知保护。"""

from contextlib import contextmanager

import pytest
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.modules.task.dao import notification_delivery_dao, task_dao
from backend.modules.task.dto.delivery_dto import DeliveryPreviewRequest, DeliverySubmitRequest
from backend.modules.task.dto.task_dto import TaskBoardQuery
from backend.modules.task.entity import tasks as task_table
from backend.modules.task.policy.delivery_policy import ACTIVE
from backend.modules.task.service import board_facts
from backend.modules.task.service.delivery_submit_service import DeliverySubmitService
from backend.modules.task.service.task_board_service import TaskBoardService
from backend.tests.delivery_fixtures import Channel
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_supplier_tasks import archive, body
from backend.tests.test_supplier_tasks import grouped as grouped
from backend.tests.test_task import USER, approve
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from sqlalchemy import event, update


@contextmanager
def statements(engine):
    found = []

    def record(connection, cursor, statement, parameters, context, many):
        found.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield found
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_detail_query_count_does_not_grow_with_members(grouped, engine, ns, app_services):
    tasks, groups, _ = grouped
    with statements(engine) as initial:
        before = groups.detail(tasks[0]["id"])
    save(
        ns,
        engine,
        bundle(
            [purchase(str(202 + index), str(872 + index)) for index in range(6)],
            [customs(str(872 + index)) for index in range(6)],
        ),
    )
    for index in range(6):
        approve(app_services, f"CD{872 + index}")
    with statements(engine) as expanded:
        after = groups.detail(tasks[0]["id"])
    assert len(before.memberTasks) == 2 and len(after.memberTasks) == 8
    assert len(after.documents) == 8 and len(after.lines) == 16
    assert len(initial) == len(expanded) <= 30
    assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in expanded)
    assert not app_services["contracts"].calls


@pytest.mark.parametrize("group_by", ["supplier", "declaration"])
def test_pagination_only_loads_current_page_and_keeps_global_counts(
    grouped, engine, ns, app_services, monkeypatch, group_by
):
    tasks, _, _ = grouped
    other = purchase("202", "872")
    other[1]["custrecord_swc_subpo_vendor"] = {"id": "88", "refName": "北京供应商"}
    save(ns, engine, bundle([other], [customs("872")]))
    approve(app_services, "CD872")
    with engine.begin() as connection:
        connection.execute(
            update(task_table).where(task_table.c.id == tasks[1]["id"]).values(status="partially_received")
        )
    board = TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])
    full = board.browse(TaskBoardQuery(groupBy=group_by))
    inspected, named = [], []
    original_guard, original_names = board_facts.changed_task_ids, app_services["tasks"].names

    def guard(connection, lines):
        inspected.append({str(line["task_id"]) for line in lines})
        return original_guard(connection, lines)

    def names(tasks, lines):
        named.append({str(row["id"]) for row in tasks})
        return original_names(tasks, lines)

    monkeypatch.setattr(board_facts, "changed_task_ids", guard)
    monkeypatch.setattr(app_services["tasks"], "names", names)
    collected = []
    for number in range(1, full.total + 1):
        page = board.browse(TaskBoardQuery(groupBy=group_by, page=number, pageSize=1))
        expected = page.items[0].taskIds if group_by == "supplier" else [page.items[0].task.id]
        assert inspected[-1] == named[-1] == set(expected)
        assert page.nodes == full.nodes and page.openTotal == full.openTotal and page.total == full.total
        collected.extend(page.items)
    assert collected == full.items
    for node in full.nodes:
        selected = board.browse(TaskBoardQuery(groupBy=group_by, node=node.key))
        assert selected.items == [item for item in full.items if item.currentNode == node.key]
        assert selected.nodes == full.nodes
    empty = board.browse(TaskBoardQuery(groupBy=group_by, page=999, pageSize=1))
    assert not empty.items and empty.total == full.total and empty.nodes == full.nodes


def test_bulk_detail_keeps_unknown_delivery_guard_for_successor(grouped, engine, ns, app_services):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    settings = Settings(wecom_send_enabled=True, subpo_archive_root=app_services["tasks"].archive.root)
    app_services["tasks"].settings = settings
    notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    channel = Channel()
    channel.create_error = ApiError(502, "结果未知")
    submit = DeliverySubmitService(engine, settings, channel, app_services["tasks"])
    preview = submit.preview(tasks[0]["id"], DeliveryPreviewRequest(revision=1, groupRevision=1), USER)
    result = submit.submit(
        tasks[0]["id"],
        DeliverySubmitRequest(
            revision=1, groupRevision=1, snapshotSha256=preview.snapshotSha256, requestId="query-test"
        ),
        USER,
    )
    assert result.status == "unknown"
    save(ns, engine, bundle([purchase("201", "871", amounts=("99.00", "20.00"))], [customs("871")]))
    approve(app_services, "CD871")
    current = [row["id"] for row in rows(engine, "SELECT * FROM task_tasks") if row["status"] != "superseded"]
    with engine.connect() as connection:
        histories, blocked, _ = notification_delivery_dao.detail_by_tasks(connection, current, ACTIVE)
        for task_id in current:
            assert histories[task_id] == notification_delivery_dao.history(connection, task_id)
            assert (task_id in blocked) == bool(
                notification_delivery_dao.overlapping(connection, task_id, ACTIVE)
            )
        details, _ = app_services["tasks"].details(connection, task_dao.by_ids(connection, current))
    assert set(current) == blocked
    assert all(
        not detail.notification.edit.allowed and not detail.notification.send.allowed for detail in details
    )
    assert len(channel.creates) == 1


def test_supplier_pagination_keeps_completed_scope_separate(grouped, engine, app_services):
    tasks, groups, _ = grouped
    with engine.begin() as connection:
        connection.execute(
            update(task_table).where(task_table.c.id == tasks[0]["id"]).values(status="completed")
        )
    board = TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])
    open_page = board.browse(TaskBoardQuery(groupBy="supplier", pageSize=1))
    done_page = board.browse(TaskBoardQuery(groupBy="supplier", node="done", pageSize=1))
    scoped = board.browse(TaskBoardQuery(groupBy="supplier", stage="completed", pageSize=1))
    assert open_page.openTotal == open_page.total == 1
    assert open_page.items[0].taskIds == [str(tasks[1]["id"])]
    assert done_page.items[0].taskIds == [str(tasks[0]["id"])]
    assert done_page.total == 1 and done_page.openTotal == 1
    assert {node.key: node.count for node in done_page.nodes}["done"] == 1
    assert scoped.items == done_page.items and scoped.total == 1 and scoped.openTotal == 0
    assert len(groups.detail(tasks[0]["id"]).memberTasks) == 1
    assert groups.detail(tasks[0]["id"], completed=True).memberTasks[0].id == str(tasks[0]["id"])
