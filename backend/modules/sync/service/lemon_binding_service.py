"""已有账号绑定用例；单 API 进程中的短期回调上下文，结果持久化。"""

import hashlib
import secrets
import time
from threading import Lock

from sqlalchemy.exc import IntegrityError

from backend.core.errors import ApiError

from ..dao import lemon_binding_dao as dao
from ..policy.lemon_binding_policy import configuration_reason, mask_mobile


class LemonBindingService:
    def __init__(self, settings, engine, client):
        self.settings, self.engine, self.client = settings, engine, client
        self.pending = {}
        self.lock = Lock()

    def _scope(self, owner):
        return hashlib.sha256(
            f"{self.settings.lemon_host}|{self.settings.lemon_app_id}|{owner}".encode()
        ).hexdigest()

    def _check(self, owner):
        if owner != f"user:{self.settings.admin_user}":
            raise ApiError(403, "只有本系统管理员可以配置柠檬云绑定")
        reason = configuration_reason(self.settings)
        if reason:
            raise ApiError(503, reason)

    def _attempt(self, cookie, owner=None):
        attempt = self.pending.get(cookie)
        if not attempt or attempt["expires"] <= time.monotonic():
            self.pending.pop(cookie, None)
            raise ApiError(409, "绑定流程已过期或服务已重启，请重新发起授权")
        if owner is not None and attempt["owner"] != owner:
            raise ApiError(403, "绑定流程不属于当前身份")
        return attempt

    def status(self, owner, cookie=None):
        if owner != f"user:{self.settings.admin_user}":
            raise ApiError(403, "只有本系统管理员可以配置柠檬云绑定")
        reason = configuration_reason(self.settings)
        scope = self._scope(owner)
        with self.engine.connect() as connection:
            row = dao.get(connection, scope)
        with self.lock:
            attempt = self.pending.get(cookie)
            if attempt and (attempt["owner"] != owner or attempt["expires"] <= time.monotonic()):
                attempt = None
            phase = "unbound" if not row else row["status"]
            if phase == "unbound" and attempt:
                phase = "awaiting_confirmation" if attempt.get("code") else "awaiting_authorization"
        messages = {
            "unbound": "尚未绑定柠檬云账号",
            "awaiting_authorization": "等待在柠檬云页面登录授权",
            "awaiting_confirmation": "已收到授权，请确认绑定",
            "binding": "绑定请求已提交；如服务中断，请先核实状态",
            "unknown": "绑定结果未知，请先核实状态，不能重复提交",
            "bound": "已有账号已绑定；可在下方选择账套手动拉票",
        }
        return {
            "phase": phase,
            "message": messages[phase],
            "mobile": mask_mobile(row["mobile"]) if row else "",
            "confirmationMobile": attempt["mobile"] if attempt and phase == "awaiting_confirmation" else "",
            "verifiedAt": row["verified_at"].isoformat() + "Z" if row and row["verified_at"] else None,
            "redirectUri": self.settings.lemon_redirect_uri,
            "begin": {
                "allowed": not reason
                and phase in ("unbound", "awaiting_authorization", "awaiting_confirmation"),
                "reason": reason
                or (
                    "可重新发起授权，之前的授权流程将失效"
                    if phase.startswith("awaiting")
                    else messages[phase]
                ),
            },
            "confirm": {
                "allowed": not reason and phase == "awaiting_confirmation",
                "reason": reason or messages[phase],
            },
            "verify": {
                "allowed": not reason and row is not None,
                "reason": reason or "仅查询已有账号与当前应用的绑定关系",
            },
            "sync": {
                "allowed": False,
                "reason": "已支持后台多账套拉取和定时计划；专业版可补全商品明细，默认版明细与附件尚未接入",
            },
        }

    def begin(self, owner, mobile):
        self._check(owner)
        scope = self._scope(owner)
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if v["expires"] > time.monotonic()}
            if any(v["scope"] == scope and v["executing"] for v in self.pending.values()):
                raise ApiError(409, "绑定处理中，请勿重新授权")
            if len(self.pending) >= 100:
                raise ApiError(429, "等待授权的请求过多，请稍后再试")
            try:
                with self.engine.begin() as connection:
                    row = dao.get(connection, scope)
                    if row and row["status"] != "unbound":
                        raise ApiError(409, "已有绑定记录或结果待核实，请先核实状态")
                    dao.prepare(connection, scope, owner, mobile)
            except IntegrityError:
                raise ApiError(409, "已有绑定请求，请刷新后查看状态") from None
            self.pending = {k: v for k, v in self.pending.items() if v["scope"] != scope}
            cookie = secrets.token_urlsafe(32)
            self.pending[cookie] = {
                "owner": owner,
                "scope": scope,
                "mobile": mobile,
                "expires": time.monotonic() + 600,
                "code": None,
                "executing": False,
            }
        return cookie, {"authorizationUrl": self.client.authorization_url(mobile)}

    def callback(self, cookie, code):
        # 官方仅承诺返回 code，不假设会回传 state。临时 Cookie 绑定浏览器；
        # 回调只接收授权码，真正绑定仍需原认证身份、同源 POST 与密码确认。
        if not code or len(code) > 2048:
            return False
        with self.lock:
            try:
                attempt = self._attempt(cookie)
            except ApiError:
                return False
            if attempt["code"] is not None or attempt["executing"]:
                return False
            attempt["code"] = code
        return True

    def confirm(self, owner, cookie, password):
        self._check(owner)
        with self.lock:
            attempt = self._attempt(cookie, owner)
            if not attempt["code"] or attempt["executing"]:
                raise ApiError(409, "请先完成授权，且不要重复提交绑定")
            attempt["executing"] = True
            snapshot = dict(attempt)
        # 应用鉴权失败时尚未提交绑定，可以保留授权码供修复后确认。
        try:
            token = self.client.app_token()
        except ApiError:
            with self.lock:
                attempt["executing"] = False
            raise
        with self.lock:
            self._attempt(cookie, owner)
        with self.engine.begin() as connection:
            if not dao.transition(connection, snapshot["scope"], ("unbound",), "binding", snapshot["mobile"]):
                raise ApiError(409, "绑定已提交或已完成，请核实状态")
        with self.lock:
            self.pending.pop(cookie, None)
        try:
            self.client.bind(token, snapshot["mobile"], snapshot["code"], password)
        except ApiError as error:
            self._finish(snapshot["scope"], "unknown" if error.status >= 500 else "unbound")
            raise
        self._finish(snapshot["scope"], "bound")
        return self.status(owner)

    def _finish(self, scope, status):
        with self.engine.begin() as connection:
            dao.transition(connection, scope, ("binding",), status)

    def verify(self, owner, cookie=None):
        self._check(owner)
        scope = self._scope(owner)
        with self.lock:
            if any(v["scope"] == scope and v["executing"] for v in self.pending.values()):
                raise ApiError(409, "绑定请求处理中，请稍后核实")
        with self.engine.connect() as connection:
            row = dao.get(connection, scope)
        if not row:
            raise ApiError(409, "请先填写账号并发起授权")
        self.client.verify(row["mobile"])
        with self.engine.begin() as connection:
            if not dao.transition(
                connection, scope, ("unbound", "binding", "unknown", "bound"), "bound", row["mobile"]
            ):
                raise ApiError(409, "账号已变化，请刷新状态后重新核实")
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if v["scope"] != scope}
        return self.status(owner, cookie)
