"""跨实例同步互斥须在专用 MySQL 验证，未配置时明确跳过。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from backend.modules.task.service.wecom_directory_service import WecomDirectoryService
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_wecom_directory import Adapter


def test_two_consumers_share_one_sync_and_search_remains_available(engine):
    adapter = Adapter()
    first, second = WecomDirectoryService(engine, adapter), WecomDirectoryService(engine, adapter)
    started, release = Event(), Event()

    def slow():
        started.set()
        assert release.wait(20)

    adapter.on_progress = slow
    first.groups()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first.run_once)
        try:
            assert started.wait(10)
            assert second.groups(refresh=True)["directoryState"] == "details"
            second.run_once()
            assert adapter.calls == 1
        finally:
            release.set()
        future.result(timeout=10)
    second.run_once()
    assert adapter.calls == 1 and len(second.groups()["items"]) == 1
