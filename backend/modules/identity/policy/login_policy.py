"""飞书登录规则：操作者标识、回跳地址、在职状态与登录资格。"""

import posixpath
from urllib.parse import unquote, urlsplit

FEISHU_PREFIX = "user:fs:"
DEFAULT_RETURN = "/workbench"
LOGIN_PATH = "/login"


def feishu_actor(user_id):
    return FEISHU_PREFIX + user_id


def feishu_user_id(actor):
    return actor[len(FEISHU_PREFIX) :] if actor.startswith(FEISHU_PREFIX) else None


def safe_return_path(value):
    """只接受站内相对路径；外部地址、协议相对地址和登录页一律回到工作台。"""
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or len(value) > 500
        or any(char.isspace() or char == "\\" for char in value)
    ):
        return DEFAULT_RETURN
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_RETURN
    # 解码并规整 ../ 后再判断，避免 /%6cogin、/tasks/../login 绕回登录页
    if posixpath.normpath(unquote(parts.path)).rstrip("/").lower() == LOGIN_PATH:
        return DEFAULT_RETURN
    return value


def inactive_reason(status):
    """飞书人员状态转为不可登录原因；可登录时返回 None。"""
    status = status if isinstance(status, dict) else {}
    if status.get("is_resigned"):
        return "已离职"
    if status.get("is_exited"):
        return "已退出企业"
    if status.get("is_frozen"):
        return "已被冻结"
    if status.get("is_activated") is False:
        return "飞书账号尚未激活"
    return None


def login_denial(user, roles):
    """不能登录的原因；可以登录时返回 None。"""
    if user is None:
        return "你不在系统使用范围内，请联系系统管理员同步你所在的部门"
    if not user["active"]:
        return f"你的账号当前不可用（{user['inactive_reason'] or '已停用'}），请联系系统管理员"
    if not roles:
        return "你还没有分配角色，请联系系统管理员开通权限"
    return None
