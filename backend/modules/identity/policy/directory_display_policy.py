"""人员页的三个展示分组；不参与同步范围、角色继承或登录资格计算。"""

from .department_policy import ancestors, subtree

DIRECTORY_GROUPS = (
    ("purchase", "采购部门", {"采购", "采购部", "采购组"}),
    ("finance", "财务部门", {"财务", "财务部"}),
    ("intelligence", "智能化部门", {"智能化部", "数字与智能化部"}),
)


def directory_groups(departments):
    """按明确名称定位实际部门，隐藏组织上级；同组嵌套部门只保留最上层入口。"""
    active = [row for row in departments if row["active"]]
    parents = {row["open_department_id"]: row["parent_open_id"] for row in active}
    result = []
    for key, label, names in DIRECTORY_GROUPS:
        matches = {row["open_department_id"] for row in active if row["name"].strip() in names}
        roots = matches - {
            open_id for open_id in matches if set(ancestors(parents.get(open_id), parents)) & matches
        }
        result.append(
            {
                "key": key,
                # 筛选分类仅用于定位，展示名称始终来自飞书部门副本。
                "label": "、".join(
                    sorted({row["name"] for row in active if row["open_department_id"] in roots})
                )
                or f"{label}（未匹配）",
                "departmentIds": sorted(row["id"] for row in active if row["open_department_id"] in roots),
            }
        )
    return result


def display_group_users(users, memberships, departments, selected):
    """筛选在分页前执行；成员去重，部门列显示范围内实际所属部门的飞书原名。"""
    rows = list(departments)
    parents = {row["open_department_id"]: row["parent_open_id"] for row in rows if row["active"]}
    groups = directory_groups(rows)
    covered = {}
    for group in groups:
        roots = [row["open_department_id"] for row in rows if row["id"] in group["departmentIds"]]
        branch = subtree(roots, parents)
        covered[group["key"]] = {row["id"] for row in rows if row["open_department_id"] in branch}
    wanted = set().union(*(ids for key, ids in covered.items() if selected in ("all", key)))
    return [
        user.model_copy(
            update={
                "departments": list(
                    dict.fromkeys(
                        row["name"]
                        for group in groups
                        for row in rows
                        if row["id"] in covered[group["key"]] & memberships.get(user.id, set())
                    )
                )
            }
        )
        for user in users
        if wanted & memberships.get(user.id, set())
    ]
