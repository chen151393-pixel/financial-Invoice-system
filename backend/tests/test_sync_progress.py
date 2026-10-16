"""进度只报告真实阶段，身份隔离、单次消费且不触发保存重试。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from backend.core.errors import ApiError
from backend.modules.sync.dto.source_dto import PullRequest
from backend.modules.sync.pull_service import PullService
from backend.modules.sync.service.progress_service import ProgressService
from backend.tests.test_sync_pull import sync_api as sync_api


def test_owner_single_use_expiry_and_running_retention():
    now = [0]
    progress = ProgressService(clock=lambda: now[0])
    identity = progress.create("owner")["progressId"]
    with pytest.raises(ApiError):
        progress.get(identity, "other")
    with progress.track(identity, "owner") as report:
        report("读取明细", 2, 5)
        now[0] = 601
        progress.create("other")
        assert progress.get(identity, "owner")["completed"] == 2
        with pytest.raises(ApiError, match="已发起"):
            with progress.track(identity, "owner"):
                pytest.fail("重复请求不能执行")
    assert progress.get(identity, "owner")["state"] == "completed"
    now[0] += 10
    assert progress.get(identity, "owner")["elapsedSeconds"] == 601
    now[0] += 590
    with pytest.raises(ApiError):
        progress.get(identity, "owner")


def test_progress_waits_for_save_and_does_not_retry_unknown_commit():
    entered, release = Event(), Event()

    class Storage:
        calls = 0

        def sync_page(self, kind, read, *, progress):
            self.calls += 1
            progress("保存到本地数据库，等待整批提交")
            entered.set()
            assert release.wait(5)
            raise ApiError(503, "MySQL保存未能确认")

    storage = Storage()
    service = PullService(None, None, storage)
    identity = service.progress.create("owner")["progressId"]
    request = PullRequest(progressId=identity)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.pull_and_save, "customs-declarations", request, "owner")
        assert entered.wait(5)
        assert service.progress.get(identity, "owner")["state"] == "running"
        release.set()
        with pytest.raises(ApiError, match="未能确认"):
            future.result()
    assert service.progress.get(identity, "owner")["state"] == "failed"
    with pytest.raises(ApiError, match="已发起"):
        service.pull_and_save("customs-declarations", request, "owner")
    assert storage.calls == 1


def test_progress_http_auth_and_safe_snapshot(sync_api):
    client, headers, _, calls = sync_api
    path = "/api/sync/ns/progress"
    assert client.post(path, json={}).status_code == 401
    response = client.post(path, headers=headers, json={})
    assert response.status_code == 200
    identity = response.json()["progressId"]
    assert client.get(f"{path}/{identity}").status_code == 401
    result = client.get(f"{path}/{identity}", headers=headers).json()
    assert result["state"] == "pending" and "owner" not in result
    assert client.get(f"{path}/missing", headers=headers).status_code == 404
    assert calls == []
