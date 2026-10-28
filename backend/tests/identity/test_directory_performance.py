"""组织读取并发、请求合并和失败恢复；不访问真实飞书或生产数据库。"""

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock
from time import sleep

import pytest
from backend.core.errors import ApiError
from backend.modules.identity.service import directory_preview_service
from backend.modules.identity.service.directory_preview_service import DirectoryPreviewService
from backend.modules.identity.service.directory_reader import read_directory
from backend.tests.identity.test_feishu_login import FakeFeishu


def test_directory_reads_concurrently_with_bounded_workers_and_complete_result():
    class MeasuredFeishu(FakeFeishu):
        def __init__(self):
            super().__init__()
            self.lock = Lock()
            self.active = self.peak = self.calls = 0

        def department_users(self, uid):
            with self.lock:
                self.active += 1
                self.calls += 1
                self.peak = max(self.peak, self.active)
            try:
                sleep(0.02)
                return super().department_users(uid)
            finally:
                with self.lock:
                    self.active -= 1

    feishu = MeasuredFeishu()
    payload = read_directory(feishu)
    assert feishu.calls == len(feishu.departments)
    assert 1 < feishu.peak <= 3
    assert payload == read_directory(FakeFeishu())


@pytest.mark.parametrize("failure", [False, True])
def test_overlapping_refresh_shares_read_and_releases_after_failure(monkeypatch, failure):
    followers_ready = Event()
    counter_lock = Lock()
    waiting = 0
    calls = 0
    payload = {"departments": [], "members": {}}

    class ObservedFuture(Future):
        def result(self, timeout=None):
            nonlocal waiting
            with counter_lock:
                waiting += 1
                if waiting == 3:
                    followers_ready.set()
            return super().result(timeout)

    def read(_):
        nonlocal calls
        calls += 1
        assert followers_ready.wait(3), "并发刷新未合并到同一次读取"
        if failure:
            raise ApiError(502, "飞书读取失败")
        return payload

    monkeypatch.setattr(directory_preview_service, "Future", ObservedFuture)
    monkeypatch.setattr(directory_preview_service, "read_directory", read)
    service = DirectoryPreviewService(None, None, FakeFeishu())
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(service._read_directory) for _ in range(4)]
        for job in jobs:
            if failure:
                with pytest.raises(ApiError, match="飞书读取失败"):
                    job.result(timeout=5)
            else:
                assert job.result(timeout=5) == payload
    assert calls == 1
    # 完成后不复用旧结果；故障不留下永久占用的刷新状态。
    monkeypatch.setattr(directory_preview_service, "read_directory", lambda _: payload)
    assert service._read_directory() == payload
