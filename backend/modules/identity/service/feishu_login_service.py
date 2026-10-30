"""飞书网页授权登录。

顺序：短事务登记一次性 state → 浏览器去飞书授权 → 回调时短事务占用 state →
事务外向飞书换取身份 → 短事务校验在职、同步范围与角色并记录审计 → 签发会话。
失败原因写入登录流程，登录页通过同一浏览器的流程 Cookie 读取，地址栏不带参数。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import audit_dao, login_flow_dao, user_dao
from ..policy.login_policy import LOGIN_PATH, feishu_actor, login_denial, safe_return_path

FLOW_MINUTES = 10


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class LoginFailed(Exception):
    def __init__(self, reason, actor="anonymous"):
        super().__init__(reason)
        self.reason, self.actor = reason, actor


class FeishuLoginService:
    def __init__(self, engine, feishu, identity, access, settings):
        self.engine, self.feishu, self.identity = engine, feishu, identity
        self.access, self.settings = access, settings

    def start(self, return_to, origin):
        """返回 (飞书授权地址, 流程 Cookie 值)。"""
        self.identity.check_origin(origin)
        if not self.feishu.configured:
            raise ApiError(503, "飞书登录尚未配置，请联系系统管理员")
        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        url = self.feishu.authorize_url(state)
        now = _now()
        try:
            with transaction(self.engine, "identity") as connection:
                login_flow_dao.purge_before(connection, now - timedelta(days=1))
                login_flow_dao.create(
                    connection,
                    {
                        "state_hash": _hash(state),
                        "browser_hash": _hash(browser),
                        "return_to": safe_return_path(return_to),
                        "expires_at": now + timedelta(minutes=FLOW_MINUTES),
                    },
                    now,
                )
        except SQLAlchemyError:
            raise ApiError(503, "登录流程保存失败，请稍后重试") from None
        return url, browser

    def callback(self, *, code, state, error, browser):
        """返回 (会话令牌或 None, 跳转路径)。"""
        flow = self._claim(state, browser)
        if flow is None:
            return None, LOGIN_PATH
        try:
            if error:
                raise LoginFailed("你取消了飞书授权，未登录")
            if not code:
                raise LoginFailed("飞书未返回授权码，请重新登录")
            user_id = self._feishu_user_id(code)
            actor = feishu_actor(user_id)
            self._admit(flow, user_id)
        except LoginFailed as failure:
            self._fail(flow, failure.reason, failure.actor)
            return None, LOGIN_PATH
        return self.identity.issue(actor), flow["return_to"]

    def _claim(self, state, browser):
        """占用一次性 state；不存在、已用、过期或不是同一浏览器发起的流程一律拒绝。"""
        if not state or not browser:
            return None
        now = _now()
        try:
            with transaction(self.engine, "identity") as connection:
                flow = login_flow_dao.by_state(connection, _hash(state), lock=True)
                if flow is None:
                    return None
                if flow["browser_hash"] != _hash(browser):
                    # 授权码属于另一个浏览器发起的流程，不改动该流程，避免被他人提前作废。
                    return None
                if flow["status"] != "pending":
                    return None
                if flow["expires_at"] <= now:
                    login_flow_dao.finish(
                        connection, flow["id"], "failed", "登录已超时，请重新登录", None, now
                    )
                    return None
                login_flow_dao.finish(connection, flow["id"], "checking", None, None, now)
                return flow
        except SQLAlchemyError:
            return None

    def _feishu_user_id(self, code):
        try:
            info = self.feishu.user_info(self.feishu.exchange_code(code))
        except ApiError as failure:
            raise LoginFailed(failure.message) from None
        tenant = self.settings.feishu_tenant_key
        if tenant and info.get("tenant_key") != tenant:
            raise LoginFailed("该飞书账号不属于本企业，不能登录")
        user_id = info.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise LoginFailed("飞书未返回用户 ID，请管理员为应用开通“获取用户 user ID”权限")
        return user_id

    def _admit(self, flow, user_id):
        now = _now()
        try:
            with transaction(self.engine, "identity") as connection:
                user, roles = self.access.principal(connection, user_id)
                reason = login_denial(user, roles)
                if reason:
                    raise LoginFailed(reason, feishu_actor(user_id))
                user_dao.touch_login(connection, user["id"], now)
                audit_dao.add(
                    connection, feishu_actor(user_id), "login", str(user["id"]), {"roles": roles}, now
                )
                login_flow_dao.finish(connection, flow["id"], "success", None, user_id, now)
        except SQLAlchemyError:
            raise LoginFailed("登录记录保存失败，请稍后重试") from None

    def _fail(self, flow, reason, actor):
        now = _now()
        try:
            with transaction(self.engine, "identity") as connection:
                login_flow_dao.finish(connection, flow["id"], "failed", reason[:300], None, now)
                audit_dao.add(connection, actor, "login_failed", None, {"reason": reason}, now)
        except SQLAlchemyError:
            pass

    def outcome(self, browser):
        """登录页读取本浏览器最近一次飞书登录的结果；只返回 10 分钟内的失败原因。"""
        if not browser:
            return {"status": "none", "reason": None}
        try:
            with self.engine.connect() as connection:
                flow = login_flow_dao.latest_for_browser(connection, _hash(browser))
        except SQLAlchemyError:
            raise ApiError(503, "登录结果读取失败，请稍后重试") from None
        if flow is None or flow["created_at"] < _now() - timedelta(minutes=FLOW_MINUTES):
            return {"status": "none", "reason": None}
        return {"status": flow["status"], "reason": flow["reason"]}
