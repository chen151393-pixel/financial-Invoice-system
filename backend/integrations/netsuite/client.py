"""NS HTTP适配器：认证缓存、读写与传输约束。"""

import logging
import math
import re
import time
from decimal import Decimal
from threading import Lock
from urllib.parse import quote

import httpx

from backend.core.config import Settings
from backend.core.errors import ApiError

from .auth import assertion
from .relation_sources import read_relation_rows

logger = logging.getLogger("ns_api.netsuite")


def log_failure(operation, method, started_at, *, error_type, status=None):
    # 不输出异常原文或 HTTP 对象，避免 URL、令牌和业务正文进入日志。
    logger.error(
        "ns_request_failed operation=%s method=%s upstream_status=%s type=%s duration_ms=%.1f",
        operation,
        method,
        status if status is not None else "-",
        error_type,
        (time.monotonic() - started_at) * 1000,
    )


class NetSuite:
    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
        self._cached = None
        self._lock = Lock()

    def close(self):
        self.client.close()

    def pl_script_query(self, payload):
        """固定只读RESTlet；不接受客户端URL/脚本编号，不重试或回退到旧口径。"""
        settings = self.settings
        if not settings.pl_restlet_script or not settings.pl_restlet_deploy:
            raise ApiError(503, "NS 同规则查询入口尚未配置，请部署 PL RESTlet 并填写脚本及部署编号")
        return self._read_restlet(settings.pl_restlet_script, settings.pl_restlet_deploy, payload)

    def finance_source_query(self, declaration_ids):
        settings = self.settings
        if not settings.finance_source_script or not settings.finance_source_deploy:
            raise ApiError(503, "原始报关行只读接口未配置，关联依据尚未完整")
        return self._read_restlet(
            settings.finance_source_script,
            settings.finance_source_deploy,
            {"declarationIds": declaration_ids},
        )

    def relation_rows(self, kind, ids):
        return read_relation_rows(self, kind, ids)

    def _read_restlet(self, script, deploy, payload):
        settings = self.settings
        if "restlets" not in settings.scope:
            raise ApiError(503, "NS 集成尚未配置 restlets 授权范围，请管理员完成授权")
        access_token = self.token()
        url = f"https://{settings.account}.restlets.api.netsuite.com/app/site/hosting/restlet.nl"
        started_at = time.monotonic()
        try:
            with self.client.stream(
                "POST",
                url,
                params={"script": script, "deploy": deploy},
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                json=payload,
                timeout=60,
                follow_redirects=False,
            ) as response:
                if response.status_code == 401:
                    with self._lock:
                        if self._cached and self._cached[0] == access_token:
                            self._cached = None
                if not response.is_success:
                    log_failure(
                        "restlet",
                        "POST",
                        started_at,
                        error_type="HTTPStatusError",
                        status=response.status_code,
                    )
                    raise ApiError(
                        502, f"NS 同规则查询失败（HTTP {response.status_code}），请核对部署受众及权限"
                    )
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 8 * 1024 * 1024:
                        log_failure(
                            "restlet",
                            "POST",
                            started_at,
                            error_type="ResponseTooLarge",
                            status=response.status_code,
                        )
                        raise ApiError(502, "NS 查询结果超过传输上限，未返回截断结果")
                    chunks.append(chunk)
        except httpx.HTTPError as error:
            log_failure("restlet", "POST", started_at, error_type=type(error).__name__)
            raise ApiError(502, "NS 查询连接失败或超时；前一只读请求可能仍在执行，请稍后手动查询") from None
        try:
            import json

            return json.loads(b"".join(chunks), parse_float=Decimal)
        except (ValueError, UnicodeError):
            log_failure("restlet", "POST", started_at, error_type="InvalidJSON", status=response.status_code)
            raise ApiError(502, "NS 同规则查询返回格式异常，请核对 RESTlet 部署") from None

    def token(self):
        with self._lock:
            if self._cached and self._cached[1] > time.monotonic() + 60:
                return self._cached[0]
            c = self.settings
            if c.missing():
                raise ApiError(503, "NS 配置不完整，请检查连接状态")
            try:
                signed = assertion(c, c.private_key.read_bytes())
            except OSError:
                raise ApiError(503, "无法读取 NS 私钥") from None
            started_at = time.monotonic()
            try:
                response = self.client.post(
                    c.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                        "client_assertion": signed,
                    },
                    timeout=20,
                    follow_redirects=False,
                )
            except httpx.HTTPError as error:
                log_failure("token", "POST", started_at, error_type=type(error).__name__)
                raise ApiError(502, "NS Token 请求失败或超时") from None
            if not response.is_success:
                log_failure(
                    "token", "POST", started_at, error_type="HTTPStatusError", status=response.status_code
                )
                raise ApiError(502, f"NS 认证失败（HTTP {response.status_code}），请检查证书映射和权限")
            try:
                data = response.json()
                value, expiry = data["access_token"], float(data["expires_in"])
                if not isinstance(value, str) or not value or not math.isfinite(expiry) or expiry <= 0:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                log_failure(
                    "token",
                    "POST",
                    started_at,
                    error_type="InvalidTokenResponse",
                    status=response.status_code,
                )
                raise ApiError(502, "NS Token 响应不完整") from None
            self._cached = value, time.monotonic() + expiry
            return value

    def validate(self, record_type, record_id=None):
        if (
            not isinstance(record_type, str)
            or record_type not in self.settings.record_types
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", record_type)
        ):
            raise ApiError(400, "该 NS 记录类型未获准访问")
        if record_id is not None and (
            not isinstance(record_id, str)
            or not re.fullmatch(r"(?:[0-9]{1,40}|eid:[A-Za-z0-9_-]{1,100})", record_id)
        ):
            raise ApiError(400, "NS 记录 ID 格式错误")

    def request(
        self,
        method,
        record_type,
        record_id=None,
        payload=None,
        token=None,
        *,
        query_params=None,
        exact_numbers=False,
    ):
        self.validate(record_type, record_id)
        if method not in ("GET", "POST", "PATCH"):
            raise ApiError(400, "不支持的 NS 操作")
        url = f"{self.settings.record_url}/{record_type}"
        if record_id is not None:
            url += "/" + quote(record_id, safe="")
        params = {"expandSubResources": "true"} if record_id else {"limit": "50"}
        if query_params is not None:
            if method != "GET" or record_id is not None:
                raise ApiError(400, "筛选参数只用于记录列表读取")
            params = query_params
        access_token = token or self.token()
        started_at = time.monotonic()
        try:
            response = self.client.request(
                method,
                url,
                params=params if method == "GET" else None,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                **({"json": payload} if payload is not None else {}),
                follow_redirects=False,
            )
        except httpx.HTTPError as error:
            log_failure("record", method, started_at, error_type=type(error).__name__)
            raise ApiError(502, "NS 请求失败或超时；写入结果可能需要人工核对") from None
        if response.status_code == 401:
            with self._lock:
                if self._cached and self._cached[0] == access_token:
                    self._cached = None
        if not response.is_success:
            log_failure(
                "record", method, started_at, error_type="HTTPStatusError", status=response.status_code
            )
            raise ApiError(
                404 if response.status_code == 404 else 502,
                f"NS 请求未成功（HTTP {response.status_code}）；请核对 NS 权限和字段",
            )
        try:
            data = (
                response.json(**({"parse_float": Decimal} if exact_numbers else {}))
                if response.content
                else None
            )
        except ValueError:
            log_failure("record", method, started_at, error_type="InvalidJSON", status=response.status_code)
            raise ApiError(502, "NS 返回非 JSON 响应") from None
        return {"data": data, "location": response.headers.get("location"), "status": response.status_code}

    def filtered_ids(self, record_type, field, value, *, reference=False):
        """只构造精确查询；分页不跟随远端链接，避免跨账户或主机请求。"""
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", field):
            raise ApiError(503, "PL 联查筛选字段配置无效")
        if reference:
            if not re.fullmatch(r"[0-9]{1,40}", value):
                raise ApiError(502, "NS 返回了无效的关联内部 ID")
            condition = f"{field} ANY_OF [{value}]"
        else:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
                raise ApiError(400, "PL 单号只允许字母、数字、下划线和短横线")
            condition = f'{field} IS "{value}"'
        ids = []
        seen = set()
        offset = 0
        while True:
            data = self.request(
                "GET",
                record_type,
                query_params={
                    "q": condition,
                    "limit": 100,
                    "offset": offset,
                },
            )["data"]
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ApiError(502, "NS 列表响应不完整")
            items = data["items"]
            for item in items:
                record_id = str(item.get("id", "")) if isinstance(item, dict) else ""
                if not re.fullmatch(r"[0-9]{1,40}", record_id):
                    raise ApiError(502, "NS 列表缺少有效内部 ID")
                if record_id in seen:
                    raise ApiError(502, "NS 分页数据重复，请重新查询")
                seen.add(record_id)
                ids.append(record_id)
            if len(ids) > 300:
                raise ApiError(422, "该 PL 关联记录过多，单类最多支持 300 条，请缩小业务范围")
            if not data.get("hasMore", False):
                return ids
            if not items:
                raise ApiError(502, "NS 分页未取得后续数据")
            offset += len(items)
