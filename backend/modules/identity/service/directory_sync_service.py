"""从飞书同步部门与同步范围内的成员；手动按钮与每日定时共用。

顺序：短事务登记同步记录 → 事务外读取部门 → 短事务保存部门并读出同步范围 →
事务外读取范围内各部门的直属成员 → 短事务保存人员、所属部门并停用范围外人员。
任何一步读取失败都只记录失败原因，不停用任何人员，避免接口故障把所有人踢出。
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import department_dao, sync_run_dao, user_dao
from ..policy.department_policy import subtree
from ..policy.login_policy import inactive_reason

logger = logging.getLogger(__name__)
STALE_RUN = timedelta(minutes=30)
OUT_OF_SCOPE = "已不在同步范围内"


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _text(value, limit):
    return value[:limit] if isinstance(value, str) and value else None


class DirectorySyncService:
    def __init__(self, engine, feishu):
        self.engine, self.feishu = engine, feishu

    def sync(self, trigger, actor):
        if not self.feishu.configured:
            raise ApiError(503, "飞书应用尚未配置，请填写 FEISHU_APP_ID 与 FEISHU_APP_SECRET")
        run_id = self._start(trigger, actor)
        counts = {"departments": 0, "users_added": 0, "users_updated": 0, "users_deactivated": 0}
        try:
            departments = self._read_departments()
            scoped = self._save_departments(departments, counts)
            members = self._read_members(scoped)
            self._save_members(members, counts)
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
            if not department_dao.scope_ids(connection):
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

    def _read_departments(self):
        """应用通讯录权限范围内的部门及其全部下级；已删除的部门不保存。"""
        found = {}
        for root in self.feishu.scope_department_ids():
            for item in [self.feishu.department(root), *self.feishu.child_departments(root)]:
                open_id = item.get("open_department_id")
                if (
                    not isinstance(open_id, str)
                    or not open_id
                    or (item.get("status") or {}).get("is_deleted")
                ):
                    continue
                found[open_id] = {
                    "open_department_id": open_id,
                    "parent_open_id": _text(item.get("parent_department_id"), 64),
                    "name": _text(item.get("name"), 200) or open_id,
                }
        return list(found.values())

    def _save_departments(self, departments, counts):
        """保存部门，返回同步范围内全部部门 {飞书部门 ID: 本地主键}。"""
        with transaction(self.engine) as connection:
            counts["departments"] = department_dao.save_all(connection, departments, _now())
            rows = department_dao.all_departments(connection)
            roots = department_dao.scope_ids(connection)
        active = {row["open_department_id"]: row for row in rows if row["active"]}
        parent_of = {open_id: row["parent_open_id"] for open_id, row in active.items()}
        root_open_ids = [row["open_department_id"] for row in rows if row["id"] in roots and row["active"]]
        return {open_id: active[open_id]["id"] for open_id in subtree(root_open_ids, parent_of)}

    def _read_members(self, scoped):
        """{user_id: 人员信息与所属的范围内部门}；同一人出现在多个部门时合并。"""
        members = {}
        for open_id, department_id in scoped.items():
            for item in self.feishu.department_users(open_id):
                user_id = item.get("user_id")
                if not isinstance(user_id, str) or not user_id:
                    raise ApiError(502, "飞书未返回用户 ID，请管理员为应用开通“获取用户 user ID”权限")
                member = members.setdefault(
                    user_id,
                    {
                        "user_id": user_id,
                        "open_id": _text(item.get("open_id"), 64),
                        "union_id": _text(item.get("union_id"), 64),
                        "name": _text(item.get("name"), 200) or user_id,
                        "avatar_url": _text((item.get("avatar") or {}).get("avatar_72"), 1024),
                        "inactive_reason": inactive_reason(item.get("status")),
                        "departments": set(),
                    },
                )
                member["departments"].add(department_id)
        return members

    def _save_members(self, members, counts):
        now = _now()
        with transaction(self.engine) as connection:
            seen = set()
            for member in members.values():
                reason = member["inactive_reason"]
                values = {**member, "active": reason is None}
                pk, added, changed = user_dao.save(connection, values, now)
                changed = user_dao.replace_departments(connection, pk, member["departments"], now) or changed
                seen.add(pk)
                if added:
                    counts["users_added"] += 1
                elif changed:
                    counts["users_updated"] += 1
            counts["users_deactivated"] = user_dao.deactivate_except(connection, seen, OUT_OF_SCOPE, now)
