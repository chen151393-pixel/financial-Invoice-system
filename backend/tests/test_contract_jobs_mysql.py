"""合同归档互斥在专用 MySQL 上验证，不以 SQLite 代替并发验收。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from backend.core.errors import ApiError
from backend.modules.task.service.contract_worker import ContractWorker
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_source_storage import rows
from backend.tests.test_task import USER
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved


def test_manual_save_and_two_workers_download_once(engine, app_services, approved, monkeypatch):
    entered, finish = Event(), Event()
    original = app_services["contracts"].download

    def download(*args):
        entered.set()
        assert finish.wait(20), "测试主线程未释放隔离下载"
        return original(*args)

    monkeypatch.setattr(app_services["contracts"], "download", download)
    job = rows(engine, "SELECT * FROM task_contract_jobs")[0]
    first = ContractWorker(engine, app_services["documents"])
    second = ContractWorker(engine, app_services["documents"])
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first.run_once)
        try:
            assert entered.wait(20)
            second.run_once()
            with pytest.raises(ApiError, match="正在下载"):
                app_services["documents"].prepare(job["task_id"], job["purchase_order_id"], USER)
        finally:
            finish.set()
        future.result(timeout=20)
    second.run_once()
    assert len(app_services["contracts"].calls) == 1
    assert rows(engine, "SELECT status FROM task_contract_jobs")[0]["status"] == "completed"
    assert rows(engine, "SELECT status FROM task_tasks")[0]["status"] == "notify_pending"
