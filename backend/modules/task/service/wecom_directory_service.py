"""企微目录：本地快照查询、持久队列、后台同步与原子发布。"""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock
from backend.core.errors import ApiError

from ..dao import wecom_directory_dao as dao

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "listing", "details"}
FRESH_SECONDS = 300
RETRY_SECONDS = 60
# 失去凭证或授权后不能继续用旧可见范围推荐群。
DENIED_CODES = {40001, 40014, 42001, 48002, 48009, 301002, 60020}


def now_utc():
    return datetime.now(UTC).replace(tzinfo=None)


class WecomDirectoryService:
    def __init__(self, engine, wecom):
        self.engine, self.wecom = engine, wecom
        self._lock = Lock()

    def _scope(self):
        if self.wecom is None:
            raise ApiError(503, "企微群查询尚未配置，请联系管理员")
        return self.wecom.directory_scope()

    def groups(self, *, refresh=False):
        """请求线程只访问配置与本地数据库，绝不等待企微 HTTP。"""
        scope, now = self._scope(), now_utc()
        try:
            with self.engine.begin() as connection:
                row = dao.ensure(connection, scope, now)
                if row["status"] not in ACTIVE and (refresh or row["next_sync_at"] <= now):
                    dao.change(
                        connection,
                        row["id"],
                        now,
                        status="queued",
                        discovered=0,
                        completed=0,
                        total=None,
                        error="",
                    )
                    row = dao.get(connection, scope)
                # 与发布共用目录行锁，避免元数据与群快照读到不同版本。
                items = dao.items(connection, row["id"]) if row["has_snapshot"] else []
        except SQLAlchemyError:
            raise ApiError(503, "企微本地群目录读取失败，请检查数据库及迁移状态") from None
        if self._scope() != scope:
            raise ApiError(409, "企微连接配置已变化，请重新查询")
        return {"items": items, "unavailableCount": row["unavailable_count"], **self._status(row, now)}

    @staticmethod
    def _status(row, now):
        synced = row["synced_at"]
        total, completed = row["total"], row["completed"]
        # 分页期间总量未知；只有完整快照已发布才显示 100%。
        percent = 100 if row["status"] == "ready" else (min(99, completed * 100 // total) if total else None)
        return {
            "directoryUpdatedAt": synced.replace(tzinfo=UTC).isoformat() if synced else None,
            "directoryStale": synced is None or (now - synced).total_seconds() >= FRESH_SECONDS,
            "directoryRefreshing": row["status"] in ACTIVE,
            "directoryRefreshError": row["error"],
            "directoryHasSnapshot": row["has_snapshot"],
            "directoryState": row["status"],
            "directoryDiscovered": row["discovered"],
            "directoryCompleted": completed,
            "directoryTotal": total,
            "directoryPercent": percent,
        }

    def run_once(self):
        # 未配置企微时保持安静；只有用户首次查询建立目录后才开始定期同步。
        try:
            scope = self._scope()
        except ApiError:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._with_database_lock(scope)
        finally:
            self._lock.release()

    def _with_database_lock(self, scope):
        name = hashlib.sha256(f"wecom:{self.engine.url.database}:{scope}".encode()).hexdigest()
        with self.engine.connect() as guard:
            acquired = False
            try:
                with guard.begin():
                    acquired = named_lock.acquire(guard, name)
                if not acquired:
                    return
                with self.engine.begin() as connection:
                    row = dao.get(connection, scope, lock=True)
                    now = now_utc()
                    if row is None or (row["status"] not in ACTIVE and row["next_sync_at"] > now):
                        return
                    # 命名锁已释放而状态仍在运行，说明上次进程中断；重新全量读取。
                    token = str(uuid4())
                    dao.change(
                        connection,
                        row["id"],
                        now,
                        status="listing",
                        run_token=token,
                        discovered=0,
                        completed=0,
                        total=None,
                        error="",
                    )
                self._sync(scope, row["id"], guard, name, token)
            finally:
                if acquired:
                    try:
                        with guard.begin():
                            named_lock.release(guard, name)
                    except SQLAlchemyError:
                        guard.invalidate()

    def _sync(self, scope, directory_id, guard, name, token):
        last_write = 0.0

        def progress(stage, discovered, completed, total):
            nonlocal last_write
            if self._scope() != scope:
                raise ApiError(409, "企微连接配置已变化，请重新查询")
            if completed and completed != total and monotonic() - last_write < 0.5:
                return
            with guard.begin():
                if not named_lock.owns(guard, name):
                    raise ApiError(409, "群目录同步锁已失效，请重新同步")
            with self.engine.begin() as connection:
                changed = dao.change(
                    connection,
                    directory_id,
                    now_utc(),
                    expected_token=token,
                    status=stage,
                    discovered=discovered,
                    completed=completed,
                    total=total,
                )
                if not changed:
                    raise ApiError(409, "群目录同步已由其他任务接续")
            last_write = monotonic()

        try:
            catalog = self.wecom.groups(progress=progress, expected_scope=scope)
            if self._scope() != scope:
                raise ApiError(409, "企微连接配置已变化，请重新查询")
            with guard.begin():
                if not named_lock.owns(guard, name):
                    raise ApiError(409, "群目录同步锁已失效，请重新同步")
            with self.engine.begin() as connection:
                row = dao.get(connection, scope, lock=True)
                if row["run_token"] != token:
                    raise ApiError(409, "群目录同步已由其他任务接续")
                now = now_utc()
                dao.publish(connection, directory_id, catalog, now, now + timedelta(seconds=FRESH_SECONDS))
        except ApiError as error:
            self._fail(
                directory_id,
                token,
                error.message,
                denied=error.status in (401, 403) or error.code in DENIED_CODES,
            )
        except (SQLAlchemyError, ValueError, TypeError, KeyError, OverflowError):
            # 存储与数据格式错误保留上次完整结果，不留下永久“同步中”。
            # 不记录上游异常正文，避免网络地址或凭证进入日志。
            logger.error("企微目录同步异常，目录 %s；请检查数据库和企微连接", directory_id)
            self._fail(directory_id, token, "群目录同步异常，请稍后重新同步或联系管理员")

    def _fail(self, directory_id, token, message, *, denied=False):
        now = now_utc()
        with self.engine.begin() as connection:
            dao.change(
                connection,
                directory_id,
                now,
                expected_token=token,
                status="failed",
                error=message[:500],
                next_sync_at=now + timedelta(seconds=RETRY_SECONDS),
                **({"has_snapshot": False} if denied else {}),
            )
