"""供应商开票时效：通知到发票收齐的天数，按供应商平均。"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.modules.task.policy.invoicing_speed_policy import average, task_durations
from backend.modules.task.service.supplier_profile_service import SupplierProfileService
from backend.tests.test_task import USER, draft, prepare_all, record
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from sqlalchemy import text

T0 = datetime(2026, 10, 1, 8, 0)


def reached(task_id, supplier_id, status, at):
    return {"task_id": task_id, "supplier_id": supplier_id, "to_status": status, "at": at}


def test_durations_skip_unfinished_reversed_and_old():
    rows = [
        reached(1, 7, "awaiting_invoice", T0),
        reached(1, 7, "documents_incomplete", T0 + timedelta(days=3)),
        reached(1, 7, "completed", T0 + timedelta(days=5)),  # 取首次收齐
        reached(2, 7, "awaiting_invoice", T0),
        reached(2, 7, "completed", T0 + timedelta(days=6)),
        reached(3, 8, "awaiting_invoice", T0),  # 尚未收齐
        reached(4, 8, "completed", T0),  # 没有通知记录
        reached(5, 9, "awaiting_invoice", T0 - timedelta(days=200)),
        reached(5, 9, "completed", T0 - timedelta(days=100)),  # 收齐早于统计窗口
    ]
    result = task_durations(rows, since=T0 - timedelta(days=90))
    assert {key: [float(v) for v in values] for key, values in result.items()} == {7: [3.0, 6.0]}
    assert average(result[7]) == Decimal("4.5")


def test_service_reads_task_events(engine, app_services, approved):
    task_id = approved["id"]
    prepare_all(app_services, task_id)
    app_services["notifications"].save_draft(task_id, draft(), USER)
    app_services["notifications"].record(task_id, record(), USER)
    with engine.begin() as connection:
        notified = connection.execute(
            text(
                "SELECT MIN(occurred_at) FROM task_events WHERE task_id = :t AND to_status = 'awaiting_invoice'"
            ),
            {"t": task_id},
        ).scalar()
        notified = datetime.fromisoformat(str(notified))
        connection.execute(
            text(
                "INSERT INTO task_events (task_id, from_status, to_status, actor, occurred_at, event_type,"
                " created_at, updated_at) VALUES (:t, 'awaiting_invoice', 'documents_incomplete', 'system',"
                " :at, 'status_changed', :at, :at)"
            ),
            {"t": task_id, "at": notified + timedelta(days=18)},
        )
    profiles = SupplierProfileService(engine, app_services["tasks"].directory)
    now = (notified + timedelta(days=19)).replace(tzinfo=timezone.utc)
    speed = profiles.invoicing_speed(now=now)
    assert speed.windowDays == 90 and speed.taskCount == 1 and speed.average == "18.0"
    [item] = speed.suppliers
    assert item.days == "18.0" and item.tasks == 1 and item.slow and item.supplier != "供应商待确认"
    assert profiles.invoicing_speed(now=now + timedelta(days=120)).taskCount == 0
