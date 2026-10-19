"""单批同步的 NS 请求与阶段耗时汇总；只记录类别、次数和毫秒数，不记录 URL、单据、查询或令牌。"""

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

logger = logging.getLogger("ns_api.netsuite")
_current = ContextVar("ns_request_stats", default=None)


class RequestStats:
    def __init__(self):
        self.lock = Lock()
        self.started = time.monotonic()
        # 类别 -> [次数, 总毫秒, 最长单次毫秒]
        self.totals = {}

    def add(self, category, elapsed_ms):
        with self.lock:
            entry = self.totals.setdefault(category, [0, 0.0, 0.0])
            entry[0] += 1
            entry[1] += elapsed_ms
            entry[2] = max(entry[2], elapsed_ms)

    def summary(self):
        with self.lock:
            return " ".join(
                f"{name}={count}/{total:.0f}ms/max{longest:.0f}ms"
                for name, (count, total, longest) in sorted(self.totals.items())
            )


def record_request(operation, started_at):
    """成功的 NS 请求计入当前批次；失败请求仍由 client.log_failure 记录。"""
    elapsed = (time.monotonic() - started_at) * 1000
    logger.debug("ns_request_completed operation=%s duration_ms=%.1f", operation, elapsed)
    stats = _current.get()
    if stats is not None:
        stats.add(f"ns_{operation}", elapsed)


@contextmanager
def phase(name):
    """记录批次内非 NS 阶段（等待锁、写库）的耗时；不在批次内时不做任何事。"""
    started = time.monotonic()
    try:
        yield
    finally:
        stats = _current.get()
        if stats is not None:
            stats.add(name, (time.monotonic() - started) * 1000)


@contextmanager
def collect(label):
    """为一个同步批次收集耗时，结束时输出一行 INFO 汇总，用于线上定位瓶颈。"""
    stats = RequestStats()
    token = _current.set(stats)
    outcome = "error"
    try:
        yield stats
        outcome = "ok"
    finally:
        _current.reset(token)
        logger.info(
            "ns_sync_timing batch=%s outcome=%s total_ms=%.0f %s",
            label,
            outcome,
            (time.monotonic() - stats.started) * 1000,
            stats.summary() or "none",
        )
