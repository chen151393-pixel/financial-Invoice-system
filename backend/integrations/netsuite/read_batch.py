"""有界只读详情读取；单次读取器复用身份，不跨保存批次缓存。"""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextvars import copy_context

from backend.core.errors import ApiError


def quiet_progress(label, completed=None, total=None):
    pass


class RecordReader:
    def __init__(self, ns, progress=None):
        self.ns = ns
        self.cache = {}
        self.progress = progress or quiet_progress

    def fetch(self, record_type, identity):
        self.ns.validate(record_type, identity)
        record = self.ns.request("GET", record_type, identity, exact_numbers=True)["data"]
        if not isinstance(record, dict) or ("id" in record and str(record["id"]) != identity):
            raise ApiError(502, "NS详情响应不完整或记录身份不一致")
        return record

    def prefetch(self, record_type, identities, label, *, on_error=None):
        ids = list(dict.fromkeys(identities))
        pending = [identity for identity in ids if (record_type, identity) not in self.cache]
        self.progress(label, len(ids) - len(pending), len(ids))
        if not pending:
            return
        workers = getattr(self.ns.settings, "sync_read_workers", 2)
        # 只保持 workers 个待执行 GET，取消总条数限制后也不会一次创建全部请求任务。
        # 全部读取完成后调用方才能校验与保存；失败不补发，已在执行的只读请求等待结束。
        remaining = iter(pending)
        completed = len(ids) - len(pending)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            try:
                while True:
                    while len(futures) < workers:
                        identity = next(remaining, None)
                        if identity is None:
                            break
                        # 复制上下文，让并发 GET 计入当前批次的耗时汇总。
                        futures[pool.submit(copy_context().run, self.fetch, record_type, identity)] = identity
                    if not futures:
                        break
                    done, _ = wait(futures, return_when=FIRST_COMPLETED)
                    for future in done:
                        identity = futures.pop(future)
                        try:
                            self.cache[record_type, identity] = future.result()
                        except ApiError as error:
                            if on_error is None or error.status not in (404, 422, 502):
                                raise
                            on_error(identity, error)
                        completed += 1
                        self.progress(label, completed, len(ids))
            finally:
                for future in futures:
                    future.cancel()

    def read(self, record_type, identity):
        if (record_type, identity) not in self.cache:
            self.prefetch(record_type, [identity], "读取单据详情")
        return self.cache[record_type, identity]
