"""群目录缓存的时效、后台并发及错误行为；使用受控时钟和内存数据。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from backend.core.errors import ApiError
from backend.integrations import wecom_group_cache as module
from backend.integrations.wecom import WeComError


@pytest.fixture
def cache(monkeypatch):
    clock = [1000]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    cache = module.WecomGroupCache()
    try:
        yield cache, clock
    finally:
        cache.close()


def catalog(name):
    return {"items": ({"groupName": name},), "unavailableCount": 0}


def test_fresh_reuse_and_stale_queries_return_without_waiting(cache):
    store, clock = cache
    calls, started, release = [], Event(), Event()

    def load():
        calls.append(1)
        if len(calls) > 1:
            started.set()
            assert release.wait(3), "缓存查询不应等待慢企微"
        return catalog("原群名" if len(calls) == 1 else "新群名")

    first = store.get("scope", load)
    assert first["directoryUpdatedAt"] and not first["directoryStale"]
    clock[0] += 299
    assert store.get("scope", load)["items"] == first["items"]
    assert len(calls) == 1
    clock[0] += 2
    try:
        stale = store.get("scope", load)
        assert started.wait(1)
        future = store._future
        assert stale["items"] == first["items"]
        assert stale["directoryStale"] and stale["directoryRefreshing"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: store.get("scope", load), range(8)))
        assert all(result["directoryRefreshing"] for result in responses)
        assert len(calls) == 2
    finally:
        release.set()
    future.result(timeout=2)
    latest = store.get("scope", load)
    assert latest["items"] == catalog("新群名")["items"]
    assert not latest["directoryStale"] and not latest["directoryRefreshing"]
    assert len(calls) == 2


def test_manual_refresh_waits_and_replaces_snapshot(cache):
    store, _ = cache
    started, release = Event(), Event()
    store.get("scope", lambda: catalog("原群名"))

    def load():
        started.set()
        assert release.wait(3)
        return catalog("新群名")

    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(store.get, "scope", load, refresh=True)
        try:
            assert started.wait(1)
            assert not request.done()
            assert store.get("scope", load)["items"] == catalog("原群名")["items"]
        finally:
            release.set()
        assert request.result(timeout=2)["items"] == catalog("新群名")["items"]


def test_refresh_failure_keeps_snapshot_with_error_and_retry_cooldown(cache):
    store, clock = cache
    store.get("scope", lambda: catalog("原群名"))
    clock[0] += 301
    calls = []

    def fail():
        calls.append(1)
        raise ApiError(502, "无法连接企微")

    with pytest.raises(ApiError, match="无法连接企微"):
        store.get("scope", fail, refresh=True)
    result = store.get("scope", fail)
    assert result["items"] == catalog("原群名")["items"]
    assert result["directoryRefreshError"] == "无法连接企微"
    assert result["directoryStale"] and not result["directoryRefreshing"]
    assert len(calls) == 1
    # 人工刷新可跳过冷却，失败仍不能假报成功。
    with pytest.raises(ApiError):
        store.get("scope", fail, refresh=True)
    assert len(calls) == 2


def test_snapshot_older_than_one_day_is_not_returned_on_failure(cache):
    store, clock = cache
    store.get("scope", lambda: catalog("旧目录"))
    clock[0] += module.MAX_AGE_SECONDS

    def fail():
        raise ApiError(502, "企微不可用")

    with pytest.raises(ApiError, match="企微不可用"):
        store.get("scope", fail)


def test_credentials_scope_change_does_not_reuse_previous_directory(cache):
    store, _ = cache
    store.get(("企业A", "凭证1"), lambda: catalog("A的群"))
    result = store.get(("企业A", "凭证2"), lambda: catalog("新授权的群"))
    assert result["items"] == catalog("新授权的群")["items"]
    result = store.get(("企业B", "凭证3"), lambda: catalog("B的群"))
    assert result["items"] == catalog("B的群")["items"]


def test_old_inflight_refresh_cannot_publish_into_new_scope(cache):
    store, clock = cache
    store.get("A", lambda: catalog("A旧群"))
    clock[0] += 301
    started, release = Event(), Event()

    def load_a():
        started.set()
        assert release.wait(3)
        return catalog("A新群")

    store.get("A", load_a)
    assert started.wait(1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(store.get, "B", lambda: catalog("B群"))
        release.set()
        assert request.result(timeout=2)["items"] == catalog("B群")["items"]
    assert store.get("B", load_a)["items"] == catalog("B群")["items"]


def test_explicit_authorization_failure_invalidates_cached_directory(cache):
    store, _ = cache
    store.get("scope", lambda: catalog("旧群"))

    def denied():
        raise WeComError(48002, "无客户联系权限")

    with pytest.raises(ApiError):
        store.get("scope", denied, refresh=True)
    with pytest.raises(ApiError):
        store.get("scope", denied)


def test_cold_failure_does_not_create_empty_success(cache):
    store, _ = cache

    def fail():
        raise ApiError(502, "读取失败")

    with pytest.raises(ApiError):
        store.get("scope", fail)
    assert store.get("scope", lambda: catalog("已恢复"))["items"] == catalog("已恢复")["items"]
