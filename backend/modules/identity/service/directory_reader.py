"""事务外完整读取飞书组织；缺字段或分页失败时拒绝生成可确认快照。"""

from concurrent.futures import ThreadPoolExecutor

from backend.core.errors import ApiError

from ..policy.login_policy import inactive_reason


def read_directory(feishu):
    # 仅并发外部只读调用；解析、去重及数据库写入仍按确定顺序执行。
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="feishu-directory") as pool:
        departments = _departments(feishu, pool)
        rows = pool.map(feishu.department_users, departments)
        return _members(departments, rows)


def _departments(feishu, pool):
    departments = {}
    pending = [(item, None) for item in pool.map(feishu.department, feishu.scope_department_ids())]
    visited = set()
    while pending:
        expand = []
        for item, direct_parent in pending:
            if (item.get("status") or {}).get("is_deleted"):
                continue
            open_id, name = item.get("open_department_id"), item.get("name")
            if not open_id or not name:
                raise ApiError(502, "飞书部门名称字段缺失，请检查部门基础信息权限")
            # parent_department_id 可因字段权限而缺失；直属 children 接口本身提供父子关系。
            parent = direct_parent or item.get("parent_department_id")
            if open_id in departments:
                previous = departments[open_id]["parent_open_id"]
                if parent and previous and parent != previous:
                    raise ApiError(502, "飞书部门层级在读取期间发生变化，请重新读取")
                parent = parent or previous
            departments[open_id] = {
                "open_department_id": open_id,
                "name": name[:200],
                "parent_open_id": parent,
            }
            if open_id not in visited:
                visited.add(open_id)
                if len(visited) > 1000:
                    raise ApiError(502, "部门过多，请缩小应用通讯录范围")
                expand.append(open_id)
        children = pool.map(lambda uid: feishu.child_departments(uid, recursive=False), expand)
        pending = [(child, uid) for uid, items in zip(expand, children, strict=True) for child in items]
    return departments


def _members(departments, rows):
    members = {}
    for open_id, items in zip(departments, rows, strict=True):
        for item in items:
            user_id = item.get("user_id")
            if not user_id:
                raise ApiError(502, "飞书未返回用户 ID，请开通“获取用户 user ID”权限")
            if (
                not item.get("name")
                or not isinstance(item.get("status"), dict)
                or "is_activated" not in item["status"]
            ):
                raise ApiError(502, "飞书成员姓名或在职状态字段缺失，请检查通讯录成员字段权限")
            reason = inactive_reason(item["status"])
            member = members.setdefault(
                user_id,
                {
                    "user_id": user_id,
                    "open_id": item.get("open_id"),
                    "union_id": item.get("union_id"),
                    "name": item["name"][:200],
                    "avatar_url": (item.get("avatar") or {}).get("avatar_72"),
                    "inactive_reason": reason,
                    "departments": [],
                },
            )
            if reason:
                member["inactive_reason"] = reason
            if open_id not in member["departments"]:
                member["departments"].append(open_id)
    return {"departments": list(departments.values()), "members": members}
