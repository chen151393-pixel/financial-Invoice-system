"""采购开票任务台：节点归类与计数、节点筛选、与详情页节点一致、资料补齐提示、来源变化提示、HTTP。"""

import pytest
from backend.app import create_app
from backend.modules.task.dto.task_dto import TaskBoardQuery
from backend.modules.task.service.task_board_service import TaskBoardService
from backend.tests.documents_ready import complete_documents
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_task import USER, FakeWecom, approve, draft, prepare_all, record
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text


@pytest.fixture
def board(engine, app_services):
    return TaskBoardService(engine, app_services["tasks"].directory, app_services["tasks"])


def counts(result):
    return {node.key: node.count for node in result.nodes}


def set_status(engine, task_id, status):
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE task_tasks SET status = :s WHERE id = :i"), {"s": status, "i": task_id}
        )


def test_nodes_follow_task_facts(board, app_services, approved):
    services, task_id = app_services, approved["id"]
    first = board.browse(TaskBoardQuery())
    assert first.openTotal == 1 and counts(first)["documents"] == 1 and counts(first)["done"] == 0
    item = first.items[0]
    assert item.currentNode == "documents" and item.currentLabel == "待存合同"
    assert [step.key for step in item.steps] == [
        "review",
        "documents",
        "notification",
        "invoices",
        "comparison",
        "completion",
    ]
    assert not item.blockedReason and "SUB-200" in item.task.orderNumbers

    prepare_all(services, task_id)
    assert board.browse(TaskBoardQuery()).items[0].currentNode == "notification"
    services["notifications"].save_draft(task_id, draft(), USER)
    services["notifications"].record(task_id, record(), USER)
    after = board.browse(TaskBoardQuery())
    assert after.items[0].currentNode == "invoices" and counts(after)["invoices"] == 1
    # 任务台与详情页使用同一套节点判定
    detail = services["tasks"].detail(task_id)
    assert [(s.key, s.state, s.description) for s in detail.steps] == [
        (s.key, s.state, s.description) for s in after.items[0].steps
    ]


def test_node_filter_and_keyword(board, approved):
    assert board.browse(TaskBoardQuery(node="documents")).total == 1
    assert board.browse(TaskBoardQuery(node="invoices")).total == 0
    assert board.browse(TaskBoardQuery(node="done")).total == 0
    empty = board.browse(TaskBoardQuery(keyword="不存在"))
    assert empty.total == 0 and empty.openTotal == 0 and not empty.items
    assert board.browse(TaskBoardQuery(keyword="CD870")).total == 1


def test_completion_node_lists_missing_documents_then_done(engine, board, app_services, approved):
    task_id = approved["id"]
    prepare_all(app_services, task_id)
    app_services["notifications"].save_draft(task_id, draft(), USER)
    app_services["notifications"].record(task_id, record(), USER)
    # 发票已收齐、资料未齐（收票由比对分配驱动，此处直接置状态以隔离任务台读取）
    set_status(engine, task_id, "documents_incomplete")
    item = board.browse(TaskBoardQuery()).items[0]
    assert item.currentNode == "completion" and "回签合同" in item.missing
    assert "回签合同" in item.nextAction and "报关单" in item.nextAction
    complete_documents(engine)
    set_status(engine, task_id, "completed")
    result = board.browse(TaskBoardQuery())
    assert result.openTotal == 0 and counts(result)["done"] == 1 and not result.items
    done = board.browse(TaskBoardQuery(node="done"))
    assert done.total == 1 and done.items[0].currentNode == "done" and not done.items[0].missing


def test_source_change_is_flagged_without_blocking_read(ns, engine, board, approved):
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    item = board.browse(TaskBoardQuery()).items[0]
    assert item.blockedReason and "重新审核" in item.blockedReason


def test_reapproval_shows_only_current_task(ns, engine, board, app_services, approved):
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    approve(app_services, "CD870")
    result = board.browse(TaskBoardQuery())
    assert result.openTotal == 1 and result.items[0].task.id != str(approved["id"])


def test_query_has_no_ns_environment_filter():
    with pytest.raises(ValidationError):
        TaskBoardQuery(account="sandbox")


def test_http_board_route(context, ns, engine):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    app = create_app(context.settings, context.ns, engine, wecom=FakeWecom())
    with TestClient(app) as client:
        assert client.post("/api/tasks/board/query", json={}).status_code == 401
        headers = {"Origin": context.settings.origin}
        client.post(
            "/api/session",
            headers=headers,
            json={"username": "admin", "password": context.settings.admin_password},
        )
        item = client.post("/api/review/declarations/query", json={}, headers=headers).json()["groups"][0]
        client.post(
            f"/api/review/declarations/{item['id']}/approve",
            json={"contentSha256": item["contentSha256"]},
            headers=headers,
        )
        response = client.post("/api/tasks/board/query", json={"node": "documents"}, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1 and body["items"][0]["currentNode"] == "documents"
        assert [node["key"] for node in body["nodes"]][-1] == "done" and "accounts" not in body
        bad = client.post("/api/tasks/board/query", json={"node": "unknown"}, headers=headers)
        assert bad.status_code in (400, 422)
