"""按组登记的真实 MySQL 并发与回滚；无专用建库连接时明确跳过。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_notification_groups import browse, request
from backend.tests.test_notification_groups import (
    test_group_rolls_back_all_members_and_other_groups_continue as test_group_rolls_back_all_members_and_other_groups_continue,
)
from backend.tests.test_source_storage import rows
from backend.tests.test_supplier_tasks import archive
from backend.tests.test_supplier_tasks import grouped as grouped
from backend.tests.test_task import USER
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import ns as ns


def test_concurrent_group_replay_only_records_once(grouped, engine, app_services):
    tasks, _, _ = grouped
    archive(app_services, tasks)
    selection = request(browse(engine, app_services))
    barrier = Barrier(2)

    def record():
        barrier.wait(timeout=10)
        return app_services["notifications"].record_groups(selection, USER)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(record) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert sorted(item.recordedGroups for item in results) == [0, 1]
    assert len(rows(engine, "SELECT * FROM task_notifications")) == 2
    assert {row["status"] for row in rows(engine, "SELECT * FROM task_tasks")} == {"awaiting_invoice"}
