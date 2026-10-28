"""权限版本与同步落库，手动确认和定时同步复用同一写入流程。"""

import hashlib
import json

from ..dao import department_dao, directory_preview_dao, user_dao
from ..policy.department_policy import subtree


def version(connection):
    # 登录时间不影响预览；权限和范围变化使确认失效。
    users = [
        {key: value for key, value in row.items() if key != "last_login_at"}
        for row in user_dao.all_users(connection)
    ]
    data = [
        department_dao.all_departments(connection),
        sorted(department_dao.scope_ids(connection)),
        sorted(directory_preview_dao.user_ids(connection)),
        users,
        {str(k): sorted(v) for k, v in department_dao.roles_by_department(connection).items()},
        {str(k): sorted(v) for k, v in user_dao.roles_by_user(connection).items()},
    ]
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def current_scope(connection):
    ids = department_dao.scope_ids(connection)
    return {
        "departmentIds": sorted(
            row["open_department_id"]
            for row in department_dao.all_departments(connection)
            if row["id"] in ids
        ),
        "userIds": sorted(directory_preview_dao.user_ids(connection)),
    }


def selected_members(payload, selection):
    parents = {d["open_department_id"]: d["parent_open_id"] for d in payload["departments"]}
    covered = subtree(selection["departmentIds"], parents)
    explicit = set(selection["userIds"])
    return {
        uid: m
        for uid, m in payload["members"].items()
        if uid in explicit or covered.intersection(m["departments"])
    }


def persist(connection, payload, selection, now):
    counts = {
        "departments": department_dao.save_all(connection, payload["departments"], now),
        "users_added": 0,
        "users_updated": 0,
        "users_deactivated": 0,
    }
    department_ids = {d["open_department_id"]: d["id"] for d in department_dao.all_departments(connection)}
    seen = set()
    for member in selected_members(payload, selection).values():
        values = {**member, "active": member["inactive_reason"] is None}
        pk, added, changed = user_dao.save(connection, values, now)
        changed = (
            user_dao.replace_departments(
                connection, pk, {department_ids[d] for d in member["departments"]}, now
            )
            or changed
        )
        seen.add(pk)
        counts["users_added"] += int(added)
        counts["users_updated"] += int(changed and not added)
    counts["users_deactivated"] = user_dao.deactivate_except(connection, seen, "已不在同步范围内", now)
    return counts
