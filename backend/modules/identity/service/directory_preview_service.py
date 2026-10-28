"""先读取、再确认导入：不可变短期预览，权限版本复核与幂等提交。"""

import secrets
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import audit_dao, department_dao, directory_preview_dao, sync_run_dao, user_dao
from ..mapper.sync_run_mapper import sync_run, utc_text
from ..policy.department_policy import ancestors, subtree
from ..policy.login_policy import feishu_user_id
from . import directory_snapshot
from .directory_reader import read_directory


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def normalize(selection):
    return {key: sorted(set(selection[key])) for key in ("departmentIds", "userIds")}


class DirectoryPreviewService:
    def __init__(self, engine, identity, feishu):
        self.engine, self.identity, self.feishu = engine, identity, feishu
        self._read_lock = Lock()
        self._pending_read = None

    def _read_directory(self):
        # 合并同一服务实例同时收到的刷新；不缓存已完成结果，各操作者仍有独立预览。
        with self._read_lock:
            leader = self._pending_read is None
            if leader:
                self._pending_read = Future()
            pending = self._pending_read
        if not leader:
            return pending.result()
        try:
            payload = read_directory(self.feishu)
            pending.set_result(payload)
            return payload
        except BaseException as failure:
            # 让所有等待者收到同一失败，不吞错或用部分结果继续同步。
            pending.set_exception(failure)
            raise
        finally:
            with self._read_lock:
                self._pending_read = None

    def create(self, actor):
        self.identity.require_manage(actor)
        if not self.feishu.configured:
            raise ApiError(503, "飞书应用尚未配置")
        with self.engine.connect() as connection:
            version = directory_snapshot.version(connection)
            selection = directory_snapshot.current_scope(connection)
        payload = self._read_directory()
        stamp = now()
        preview_id = secrets.token_hex(24)
        expires = stamp + timedelta(minutes=10)
        with transaction(self.engine) as connection:
            directory_preview_dao.create(
                connection,
                {
                    "id": preview_id,
                    "actor": actor,
                    "version": version,
                    "payload": payload,
                    "expires_at": expires,
                },
                stamp,
            )
        parents = {d["open_department_id"]: d["parent_open_id"] for d in payload["departments"]}
        names = {d["open_department_id"]: d["name"] for d in payload["departments"]}
        departments = []
        for d in payload["departments"]:
            uid = d["open_department_id"]
            chain = ancestors(uid, parents)
            departments.append(
                {
                    "id": uid,
                    "name": d["name"],
                    "depth": len(chain) - 1,
                    "path": " / ".join(names[x] for x in reversed(chain)),
                    "memberCount": sum(uid in m["departments"] for m in payload["members"].values()),
                }
            )
        return {
            "id": preview_id,
            "expiresAt": utc_text(expires),
            "departments": sorted(departments, key=lambda d: d["path"]),
            "selection": {
                "departmentIds": [d for d in selection["departmentIds"] if d in parents],
                "userIds": [u for u in selection["userIds"] if u in payload["members"]],
            },
        }

    def _load(self, connection, preview_id, actor):
        row = directory_preview_dao.get(connection, preview_id)
        if row is None or row["actor"] != actor:
            raise ApiError(404, "组织预览不存在，请重新读取飞书")
        if row["expires_at"] < now():
            raise ApiError(409, "组织预览已过期，请重新读取飞书后确认")
        return row

    def _validate(self, row, selection):
        payload = row["payload"]
        ids = {d["open_department_id"] for d in payload["departments"]}
        if set(selection["departmentIds"]) - ids or set(selection["userIds"]) - payload["members"].keys():
            raise ApiError(400, "所选部门或成员不在本次飞书预览中")

    def members(self, preview_id, query, actor):
        self.identity.require_manage(actor)
        selection = normalize(query)
        with self.engine.connect() as connection:
            row = self._load(connection, preview_id, actor)
            imported = {u["user_id"] for u in user_dao.all_users(connection)}
        self._validate(row, selection)
        payload = row["payload"]
        names = {d["open_department_id"]: d["name"] for d in payload["departments"]}
        if query["departmentId"] not in names:
            raise ApiError(400, "部门不在本次飞书预览中")
        covered = subtree(
            selection["departmentIds"],
            {d["open_department_id"]: d["parent_open_id"] for d in payload["departments"]},
        )
        chosen = directory_snapshot.selected_members(payload, selection)
        rows = [
            m
            for m in payload["members"].values()
            if query["departmentId"] in m["departments"]
            and query["query"].strip().casefold() in m["name"].casefold()
        ]
        rows.sort(key=lambda m: (m["name"], m["user_id"]))
        start = (query["page"] - 1) * 50
        return {
            "items": [
                {
                    "id": m["user_id"],
                    "name": m["name"],
                    "departments": [names[d] for d in m["departments"]],
                    "selected": m["user_id"] in chosen,
                    "selectable": m["inactive_reason"] is None,
                    "reason": m["inactive_reason"],
                    "imported": m["user_id"] in imported,
                    "coveredByDepartment": bool(covered.intersection(m["departments"])),
                }
                for m in rows[start : start + 50]
            ],
            "total": len(rows),
            "page": query["page"],
            "pageSize": 50,
            "selectedCount": len(chosen),
            "coveredDepartmentIds": sorted(covered),
        }

    def _plan(self, connection, row, selection, actor):
        self._validate(row, selection)
        if row["version"] != directory_snapshot.version(connection):
            raise ApiError(409, "人员、角色或同步范围已变化，请重新读取飞书后确认")
        chosen = directory_snapshot.selected_members(row["payload"], selection)
        existing = user_dao.all_users(connection)
        known = {u["user_id"] for u in existing}
        removed = [u for u in existing if u["active"] and u["user_id"] not in chosen]
        if any(u["user_id"] == feishu_user_id(actor) for u in removed):
            raise ApiError(400, "不能将当前管理员移出同步范围，请由其他管理员操作")
        return {
            "selection": selection,
            "selectedCount": len(chosen),
            "addedCount": len(chosen.keys() - known),
            "retainedCount": len(chosen.keys() & known),
            "removedNames": [u["name"] for u in removed],
            "departmentNames": [
                d["name"]
                for d in row["payload"]["departments"]
                if d["open_department_id"] in selection["departmentIds"]
            ],
            "userNames": [row["payload"]["members"][u]["name"] for u in selection["userIds"]],
            "unavailableCount": sum(m["inactive_reason"] is not None for m in chosen.values()),
        }

    def plan(self, preview_id, selection, actor):
        self.identity.require_manage(actor)
        with self.engine.connect() as connection:
            row = self._load(connection, preview_id, actor)
            return self._plan(connection, row, normalize(selection), actor)

    def apply(self, preview_id, selection, actor):
        self.identity.require_manage(actor)
        selection = normalize(selection)
        try:
            with transaction(self.engine) as connection:
                self.identity.require_manage(actor)
                row = self._load(connection, preview_id, actor)
                if row["result"]:
                    if row["result"]["selection"] != selection:
                        raise ApiError(409, "本次预览已经确认，不能更换范围后重复提交")
                    return row["result"]["response"]
                self._plan(connection, row, selection, actor)
                stamp = now()
                before = directory_snapshot.current_scope(connection)
                counts = directory_snapshot.persist(connection, row["payload"], selection, stamp)
                ids = {d["open_department_id"]: d["id"] for d in department_dao.all_departments(connection)}
                department_dao.replace_scopes(
                    connection, {ids[d] for d in selection["departmentIds"]}, actor, stamp
                )
                directory_preview_dao.replace_users(connection, selection["userIds"], actor, stamp)
                run_id = sync_run_dao.start(connection, "manual", actor, stamp)
                sync_run_dao.finish(
                    connection, run_id, {"status": "succeeded", "error": None, **counts}, stamp
                )
                chosen = directory_snapshot.selected_members(row["payload"], selection)
                response = {
                    "run": sync_run(sync_run_dao.latest(connection)).model_dump(),
                    "userIds": [u["id"] for u in user_dao.all_users(connection) if u["user_id"] in chosen],
                }
                audit_dao.add(
                    connection,
                    actor,
                    "scope_sync",
                    preview_id,
                    {"before": before, "after": selection, **counts},
                    stamp,
                )
                directory_preview_dao.finish(
                    connection, preview_id, {"selection": selection, "response": response}, stamp
                )
                return response
        except SQLAlchemyError:
            raise ApiError(503, "同步结果保存失败，未改变人员与权限，请重试") from None
