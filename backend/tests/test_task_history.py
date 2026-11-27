"""流转记录步骤号、同刻先后、微秒时间、合并范围及操作人姓名。"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from backend.modules.identity.dao import user_dao
from backend.modules.task.dao import event_dao
from backend.modules.task.mapper import task_history_mapper
from backend.tests.test_source_storage import rows
from backend.tests.test_supplier_tasks import archive
from backend.tests.test_supplier_tasks import grouped as grouped
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from backend.tests.test_task import prepare_all
from sqlalchemy import text

ACTOR = "user:fs:11gc6fb6"
NAME = "隔离测试财务人员"


def person(connection, now):
    user_dao.save(
        connection,
        {
            "user_id": "11gc6fb6",
            "open_id": None,
            "union_id": None,
            "name": NAME,
            "avatar_url": None,
            "active": False,
            "inactive_reason": "已停用，历史记录仍显示姓名",
        },
        now,
    )


def test_history_uses_microseconds_before_event_id_and_does_not_mutate_source():
    def event(identity, at, actor=ACTOR):
        return {
            "id": identity,
            "occurred_at": datetime.fromisoformat(at),
            "actor": actor,
            "event_type": "status_changed",
            "from_status": None,
            "to_status": "documents_pending",
            "reason": "保留原审计说明",
        }

    source = [
        event(9007199254740994, "2026-11-26T06:14:31.123455"),
        event(20, "2026-11-26T06:14:31.123456"),
        event(21, "2026-11-26T06:14:31.123456", "system"),
        event(22, "2026-11-26T06:14:31.123456", "user:fs:missing"),
    ]
    original = deepcopy(source)
    result = task_history_mapper.records(source, [], {ACTOR: NAME, "system": "系统"})
    assert [record.id for record in result] == ["event:22", "event:21", "event:20", "event:9007199254740994"]
    assert [record.sequence for record in result] == [4, 3, 2, 1]
    assert [record.actorName for record in result] == ["user:fs:missing", "系统", NAME, NAME]
    assert source == original


def test_first_operation_is_step_one_and_recovery_success_follows_its_audit(engine, app_services, approved):
    task_id = approved["id"]
    prepare_all(app_services, task_id)
    at = datetime.now(UTC).replace(tzinfo=None)
    with engine.begin() as connection:
        person(connection, at)
        connection.execute(
            text("UPDATE task_events SET actor=:actor, occurred_at=:at"),
            {"actor": ACTOR, "at": at - timedelta(seconds=1)},
        )
        connection.execute(text("UPDATE task_documents SET created_at=:at, archived_at=:at"), {"at": at})
        recovered = event_dao.append(
            connection,
            {
                "task_id": task_id,
                "from_status": "documents_pending",
                "to_status": "documents_pending",
                "actor": ACTOR,
                "event_type": "contract_recovered",
                "reason": "定向补存子采购合同",
            },
            at,
        )
        completed = event_dao.append(
            connection,
            {
                "task_id": task_id,
                "from_status": "documents_pending",
                "to_status": "notify_pending",
                "actor": ACTOR,
                "reason": "合同批量补存完成，全部子采购合同已归档",
            },
            at,
        )
    before = rows(engine, "SELECT * FROM task_events ORDER BY id")
    detail = app_services["tasks"].detail(task_id)
    history = detail.history
    assert [item.id for item in history[:2]] == [f"event:{completed}", f"event:{recovered}"]
    assert [item.label for item in history[:2]] == ["子采购合同已全部保存到共享盘", "子采购合同补存成功"]
    assert history[2].kind == "document"
    assert history[-1].sequence == 1 and history[-1].label == "财务审核通过，生成开票任务"
    assert [item.sequence for item in history] == list(range(len(history), 0, -1))
    assert all(item.actor == ACTOR and item.actorName == NAME for item in history if item.kind == "event")
    assert all(event.actor == ACTOR for event in detail.events)
    assert rows(engine, "SELECT * FROM task_events ORDER BY id") == before


def test_supplier_history_numbers_all_members_and_resolves_names_once(
    grouped, engine, app_services, monkeypatch
):
    tasks, groups, _ = grouped
    archive(app_services, tasks)
    at = datetime.now(UTC).replace(tzinfo=None)
    with engine.begin() as connection:
        person(connection, at)
        connection.execute(
            text("UPDATE task_events SET actor=:actor, occurred_at=:at"), {"actor": ACTOR, "at": at}
        )
    original = user_dao.names_by_user_ids
    calls = []

    def names(connection, user_ids):
        calls.append(user_ids)
        return original(connection, user_ids)

    monkeypatch.setattr(user_dao, "names_by_user_ids", names)
    detail = groups.detail(tasks[0]["id"])
    events = [item for item in detail.history if item.kind == "event"]
    expected = rows(engine, "SELECT id FROM task_events ORDER BY id DESC")
    assert [item.id for item in events] == [f"event:{row['id']}" for row in expected]
    assert {item.actorName for item in events} == {NAME}
    assert {item.reason.split("：", 1)[0] for item in events} == {"CD870", "CD871"}
    assert len(calls) == 1 and calls[0] == ["11gc6fb6"]
    assert len({item.id for item in detail.history}) == len(detail.history)
    assert [item.sequence for item in detail.history] == list(range(len(detail.history), 0, -1))
    assert len([item for item in detail.history if item.kind == "document"]) == 2
