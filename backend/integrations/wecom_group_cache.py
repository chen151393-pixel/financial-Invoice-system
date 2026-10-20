"""企微群识别目录缓存：短期复用、过期后台刷新，不缓存成员清单。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock
from time import monotonic

from backend.core.errors import ApiError

FRESH_SECONDS = 300
MAX_AGE_SECONDS = 86400
RETRY_SECONDS = 60


class WecomGroupCache:
    def __init__(self):
        self._lock = Lock()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wecom-directory")
        self._scope = None
        self._snapshot = None
        self._loaded_at = 0
        self._updated_at = None
        self._future = None
        self._job = None
        self._error = ""
        self._retry_at = 0
        self._closed = False

    def close(self):
        with self._lock:
            self._closed = True
        self._worker.shutdown(wait=True, cancel_futures=False)

    def get(self, scope, load, *, refresh=False):
        with self._lock:
            if self._closed:
                raise ApiError(503, "企微群查询服务正在关闭")
            if scope != self._scope:
                # 企业或凭证变化后，旧目录和旧任务都不能成为新身份的查询结果。
                self._scope, self._snapshot, self._future, self._job = scope, None, None, None
                self._error, self._retry_at = "", 0
            age = monotonic() - self._loaded_at
            usable = self._snapshot is not None and age < MAX_AGE_SECONDS
            if usable and age < FRESH_SECONDS and not refresh:
                return self._view()
            if self._future is None and (refresh or not usable or monotonic() >= self._retry_at):
                job = object()
                self._job = job
                self._future = self._worker.submit(self._reload, scope, job, load)
            if usable and not refresh:
                return self._view()
            future = self._future
        # 冷启动、超过最大保留时间或手动刷新才等待；并发请求复用同一任务。
        future.result()
        with self._lock:
            if self._scope != scope or self._snapshot is None:
                raise ApiError(409, "企微连接配置已变化，请重新查询")
            return self._view()

    def _view(self):
        return {
            **self._snapshot,
            "directoryUpdatedAt": self._updated_at,
            "directoryStale": monotonic() - self._loaded_at >= FRESH_SECONDS,
            "directoryRefreshing": self._future is not None,
            "directoryRefreshError": self._error,
        }

    def _reload(self, scope, job, load):
        try:
            result = load()
        except ApiError as error:
            with self._lock:
                if self._job is job:
                    self._error = error.message
                    self._retry_at = monotonic() + RETRY_SECONDS
                    # 已明确失去授权时不继续提供旧目录；网络故障可保留有时间标记的快照。
                    if error.status in (401, 403) or error.code in (
                        40001,
                        40014,
                        42001,
                        48002,
                        48009,
                        301002,
                        60020,
                    ):
                        self._snapshot = None
            raise
        else:
            with self._lock:
                if self._scope == scope and self._job is job:
                    self._snapshot = result
                    self._loaded_at = monotonic()
                    self._updated_at = datetime.now(UTC).isoformat()
                    self._error, self._retry_at = "", 0
        finally:
            # 发布完整快照后再释放占位；失败也允许人工重试。
            with self._lock:
                if self._job is job:
                    self._future = None
