"""角色定义与生效规则（docs/feishu-identity-plan.md 第 5 节）。

第 1 期只区分“能否管理人员与权限”；其余写权限按角色细分在第 2 期落实。
"""

ROLES = {
    "admin": "系统管理员",
    "finance_manager": "财务主管",
    "finance": "财务专员",
    "purchaser": "采购专员",
    "viewer": "只读",
}

# 应急管理员账号固定拥有系统管理员角色
EMERGENCY_ROLES = ("admin",)


def unknown_roles(roles):
    return sorted(set(roles) - set(ROLES))


def ordered(roles):
    return [code for code in ROLES if code in set(roles)]


def effective_roles(department_roles, personal_roles, custom):
    """custom 为是时只按个人角色；否则为部门默认角色（含上级部门）与个人角色的并集。"""
    return ordered(personal_roles if custom else set(department_roles) | set(personal_roles))


def can_manage_access(roles):
    return "admin" in roles
