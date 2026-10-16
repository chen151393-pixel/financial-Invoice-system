"""单进程、身份隔离的临时进度；不承担持久任务、保存结果或自动重试。"""

from contextlib import contextmanager
from threading import Lock
from time import monotonic
from uuid import uuid4

from backend.core.errors import ApiError


class ProgressService:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.lock = Lock()
        self.entries = {}

    def create(self, owner):
        with self.lock:
            now = self.clock()
            self.entries = {
                key: entry
                for key, entry in self.entries.items()
                if entry["state"] == "running" or now - entry["updated"] < 600
            }
            if len(self.entries) >= 256:
                completed = [
                    key for key, value in self.entries.items() if value["state"] in {"completed", "failed"}
                ]
                if completed:
                    del self.entries[min(completed, key=lambda key: self.entries[key]["updated"])]
            if len(self.entries) >= 256:
                raise ApiError(429, "同步进度请求较多，请稍后再试")
            identity = uuid4().hex
            self.entries[identity] = {
                "owner": owner,
                "state": "pending",
                "label": "等待开始",
                "completed": None,
                "total": None,
                "started": now,
                "updated": now,
            }
            return {"progressId": identity}

    def _entry(self, identity, owner):
        entry = self.entries.get(identity)
        if (
            not entry
            or entry["owner"] != owner
            or (entry["state"] != "running" and self.clock() - entry["updated"] >= 600)
        ):
            raise ApiError(404, "本次进度已过期或不可访问；请以保存请求结果为准")
        return entry

    def get(self, identity, owner):
        with self.lock:
            entry = self._entry(identity, owner)
            return {key: entry[key] for key in ("state", "label", "completed", "total")} | {
                "elapsedSeconds": int(
                    (self.clock() if entry["state"] == "running" else entry["updated"]) - entry["started"]
                )
            }

    @contextmanager
    def track(self, identity, owner):
        with self.lock:
            entry = self._entry(identity, owner)
            if entry["state"] != "pending":
                raise ApiError(409, "该批次已发起，请核实原请求结果，不要重复提交")
            entry.update(state="running", started=self.clock())

        def report(label, completed=None, total=None):
            with self.lock:
                entry.update(label=label, completed=completed, total=total, updated=self.clock())

        try:
            yield report
        except BaseException:
            # 异常包括提交结果不明；不能根据进度宣称未写入或允许自动重发。
            with self.lock:
                entry.update(state="failed", label="本批次未确认完成，请核实保存响应", updated=self.clock())
            raise
        else:
            with self.lock:
                entry.update(
                    state="completed", label="本批次处理结束，请查看逐单保存结果", updated=self.clock()
                )
