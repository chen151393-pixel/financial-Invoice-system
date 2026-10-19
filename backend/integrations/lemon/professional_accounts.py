"""专业版网页的只读账套协议；每次调用使用独立、仅驻内存的官方会话。"""

import json
import logging

import httpx

from backend.core.errors import ApiError

logger = logging.getLogger("ns_api.lemon")
ACCOUNT_HOST = "https://api.ningmengyun.com"
SERVICE_HOST = "https://wbgate.ningmengyun.com"
PRO_HOST = "https://jproapi.ningmengyun.com"


class LemonProfessionalAccounts:
    def __init__(self, settings, session_factory=None):
        self.settings = settings
        self.session_factory = session_factory or (
            lambda: httpx.Client(timeout=20, follow_redirects=False, trust_env=False)
        )

    def query(self, token):
        if self.settings.lemon_host != "https://open2.ningmengyun.com":
            raise ApiError(422, "专业版账套查询仅支持已验证的柠檬云正式环境")
        # 不能复用进程级 Cookie 容器，避免并发用户或绑定切换串用认证上下文。
        with self.session_factory() as session:
            self._get(
                session,
                ACCOUNT_HOST + "/api/AuthorizationCookie.ashx",
                "session",
                params={"token": token},
                expect_json=False,
            )
            if not session.cookies:
                raise ApiError(502, "柠檬云未建立专业版查询会话，请核实应用授权")
            availability = self._service_data(session, "/wb/plan/haveProServiceInfo")
            if availability is False:
                # 只有上游明确确认没有专业版服务时，才允许调用方查询默认账套。
                return None
            if availability is not True:
                raise ApiError(502, "柠檬云专业版服务状态格式异常")
            context = self._service_data(
                session,
                "/wb/redirect/info",
                params={"appId": 1060, "virtualAppId": 1062, "productType": "acc"},
            )
            return self._accounts(session, context)

    def _service_data(self, session, path, params=None):
        payload = self._get(session, SERVICE_HOST + path, "service", params=params)
        if payload.get("statusCode") is not True or "data" not in payload:
            raise ApiError(502, "柠檬云未确认专业版服务查询成功，请核实授权")
        return payload["data"]

    def _accounts(self, session, context):
        service_id = context.get("serviceId") if isinstance(context, dict) else None
        if type(service_id) is not int or not 0 < service_id <= 2147483647:
            raise ApiError(502, "柠檬云未返回有效的专业版财务服务 ID，不能使用默认账套替代")
        appasid = context.get("appasid")
        if not isinstance(appasid, str) or not appasid or len(appasid) > 2048:
            raise ApiError(502, "柠檬云未返回有效的专业版账套上下文")
        payload = self._get(
            session,
            PRO_HOST + "/api/AccountSetOnlyAuth/TopInfoV2",
            "accounts",
            params={"serviceId": service_id, "appasid": appasid},
        )
        if payload.get("state") != 1000 or not isinstance(payload.get("data"), dict):
            raise ApiError(502, "柠檬云未确认专业版账套查询成功")
        rows = payload["data"].get("accountList")
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ApiError(502, "柠檬云专业版账套列表异常或超过查询上限")
        result, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                raise ApiError(502, "柠檬云专业版账套格式异常")
            asid, name = row.get("asid"), row.get("asname")
            if type(asid) is not int or asid <= 0 or not isinstance(name, str) or not name.strip():
                raise ApiError(502, "柠檬云专业版账套缺少有效编号或名称")
            if asid in seen or len(name) > 255:
                raise ApiError(502, "柠檬云专业版账套重复或名称过长")
            seen.add(asid)
            result.append({"asid": str(asid), "name": name, "edition": "professional"})
        logger.info("lemon_accounts_read source=professional count=%s", len(result))
        return result

    @staticmethod
    def _get(session, url, stage, *, params=None, expect_json=True):
        try:
            with session.stream("GET", url, params=params, follow_redirects=False) as response:
                status = response.status_code
                if status != 200:
                    logger.warning("lemon_professional_failed stage=%s upstream_status=%s", stage, status)
                    raise ApiError(
                        502, f"柠檬云专业版查询失败（阶段 {stage}，HTTP {status}），未使用默认账套替代"
                    )
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise ApiError(502, "柠檬云专业版响应超过查询上限")
                    chunks.append(chunk)
                if not expect_json:
                    return None
                payload = json.loads(b"".join(chunks))
        except (httpx.HTTPError, ValueError) as error:
            # URL 含临时令牌或加密账套；不记录异常正文、重定向地址或上游消息。
            logger.warning("lemon_professional_failed stage=%s type=%s", stage, type(error).__name__)
            raise ApiError(502, "柠檬云专业版查询连接或响应异常，未使用默认账套替代") from None
        if not isinstance(payload, dict):
            raise ApiError(502, "柠檬云专业版响应结构异常")
        return payload
