"""从飞书同步部门与同步范围内的成员；手动按钮与每日定时共用。

顺序：登记记录 → 读取权限版本和部门／个人范围 → 事务外完整读取飞书 →
短事务复核版本后保存所选人员。新导入默认未启用，已有启用状态保留。
任何一步读取失败都只记录失败原因，不停用任何人员，避免接口故障把所有人踢出。
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import department_dao, directory_preview_dao, sync_run_dao
from . import directory_snapshot
from .directory_reader import read_directory

logger = logging.getLogger(__name__)
STALE_RUN = timedelta(minutes=30)


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


class DirectorySyncService:
    def __init__(self, engine, feishu):
        self.engine, self.feishu = engine, feishu

    def sync(self, trigger, actor):
        if not self.feishu.configured:
            raise ApiError(503, "飞书应用尚未配置，请填写 FEISHU_APP_ID 与 FEISHU_APP_SECRET")
        run_id = self._start(trigger, actor)
        counts = {"departments": 0, "users_added": 0, "users_updated": 0, "users_deactivated": 0}
        try:
            with self.engine.connect() as connection:
                version = directory_snapshot.version(connection)
                selection = directory_snapshot.current_scope(connection)
            payload = read_directory(self.feishu)
            if not payload["departments"] and (selection["departmentIds"] or selection["userIds"]):
                raise ApiError(502, "飞书可见部门为空，已保留人员，请核实应用通讯录范围后重新同步")
            with transaction(self.engine) as connection:
                if version != directory_snapshot.version(connection):
                    raise ApiError(409, "同步期间人员权限或范围已变化，请重新同步")
                counts = directory_snapshot.persist(connection, payload, selection, _now())
        except (ApiError, SQLAlchemyError) as failure:
            message = (
                failure.message if isinstance(failure, ApiError) else "保存同步结果失败，请检查业务数据库"
            )
            self._finish(run_id, {"status": "failed", "error": message[:500], **counts})
            raise ApiError(502 if isinstance(failure, ApiError) else 503, message) from None
        self._finish(run_id, {"status": "succeeded", "error": None, **counts})
        return self.latest()

    def latest(self):
        try:
            with self.engine.connect() as connection:
                return sync_run_dao.latest(connection)
        except SQLAlchemyError:
            raise ApiError(503, "同步记录读取失败，请检查业务数据库") from None

    def due(self, interval):
        """定时同步：已配置同步范围，且距上次成功同步超过 interval。"""
        with self.engine.connect() as connection:
            if not department_dao.scope_ids(connection) and not directory_preview_dao.user_ids(connection):
                return False
            last = sync_run_dao.latest(connection, status="succeeded")
        return last is None or last["started_at"] <= _now() - interval

    def _start(self, trigger, actor):
        now = _now()
        try:
            with transaction(self.engine) as connection:
                running = sync_run_dao.latest(connection, status="running")
                if running and running["started_at"] > now - STALE_RUN:
                    raise ApiError(409, "飞书同步正在进行，请稍后刷新查看结果")
                return sync_run_dao.start(connection, trigger, actor, now)
        except SQLAlchemyError:
            raise ApiError(503, "同步记录保存失败，请检查业务数据库") from None

    def _finish(self, run_id, values):
        try:
            with transaction(self.engine) as connection:
                sync_run_dao.finish(connection, run_id, values, _now())
        except SQLAlchemyError:
            logger.error("identity_sync_finish_failed run=%s", run_id)
