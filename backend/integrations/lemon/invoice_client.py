"""官方 open2 用户授权、账套及进项票只读协议；令牌仅存在于本次调用中。"""

import json
import logging
import time
from decimal import Decimal

import httpx

from backend.core.errors import ApiError

from .professional_accounts import LemonProfessionalAccounts

logger = logging.getLogger("ns_api.lemon")
OPERATIONS = {
    "user_token": "获取用户授权",
    "accounts": "查询授权账套",
    "invoices": "查询进项发票",
}


class LemonInvoiceClient:
    def __init__(self, settings, binding_client, client=None, professional_session_factory=None):
        self.settings, self.binding = settings, binding_client
        self.client = client or httpx.Client(timeout=20, follow_redirects=False, trust_env=False)
        self.professional = LemonProfessionalAccounts(settings, professional_session_factory)

    def close(self):
        self.client.close()

    def _post(self, path, token, *, operation, params=None, asid=None):
        started, status = time.monotonic(), None
        page = (params or {}).get("page")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if asid is not None:
            headers["asid"] = asid
        try:
            with self.client.stream(
                "POST", self.settings.lemon_host + path, headers=headers, params=params
            ) as response:
                status = response.status_code
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise ApiError(502, "柠檬云单页响应过大，请缩小日期范围")
                    chunks.append(chunk)
                data = json.loads(b"".join(chunks), parse_float=Decimal)
        except httpx.HTTPStatusError:
            raise self._failure(operation, "http_status", started, status, page) from None
        except httpx.TimeoutException:
            raise self._failure(operation, "timeout", started, status, page) from None
        except httpx.RequestError as error:
            raise self._failure(operation, type(error).__name__, started, status, page) from None
        except ValueError:
            raise self._failure(operation, "invalid_json", started, status, page) from None
        if not isinstance(data, dict) or data.get("State") != 1000:
            envelope = data if isinstance(data, dict) else {}
            raise self._failure(
                operation,
                "business_response",
                started,
                status,
                page,
                state=envelope.get("State"),
                substate=envelope.get("SubState"),
            )
        if not isinstance(data.get("Data"), dict):
            raise self._failure(operation, "invalid_data", started, status, page)
        return data["Data"]

    @staticmethod
    def _failure(operation, kind, started, status, page, *, state=None, substate=None):
        # 只输出固定阶段及数字状态；异常文本、URL、上游 Msg 和正文可能包含密钥或票据。
        state = state if type(state) is int else None
        substate = substate if type(substate) is int else None
        logger.error(
            "lemon_read_failed operation=%s type=%s upstream_status=%s page=%s "
            "state=%s substate=%s duration_ms=%.1f",
            operation,
            kind,
            status,
            page,
            state,
            substate,
            (time.monotonic() - started) * 1000,
        )
        label = OPERATIONS[operation]
        if kind == "http_status":
            reason = f"上游返回 HTTP {status}"
        elif kind == "timeout":
            reason = "上游请求超时"
        elif kind == "invalid_json":
            reason = "上游响应不是有效 JSON"
        elif kind == "business_response":
            reason = f"上游业务未确认成功（State={state}，SubState={substate}）"
        elif kind == "invalid_data":
            reason = "上游返回数据结构异常"
        else:
            reason = "网络连接或传输失败"
        return ApiError(502, f"柠檬云{label}失败：{reason}；本次未保存发票，请查看服务器脱敏日志")

    def user_token(self, mobile):
        data = self._post(
            "/api/OAuth2/Token/GetSpecificUserToken",
            self.binding.app_token(),
            operation="user_token",
            params={"userid": mobile, "isOem": "false"},
        )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise ApiError(502, "柠檬云未返回用户授权，请核实已有绑定")
        return token

    def professional_accounts(self, token):
        return self.professional.query(token)

    def accounts(self, token):
        data = self._post(
            "/api/Settings/AccountSet/GetAccountSets",
            token,
            operation="accounts",
        )
        rows = data.get("rows")
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ApiError(502, "柠檬云账套列表异常")
        result, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                raise ApiError(502, "柠檬云账套格式异常")
            asid, name = row.get("AsId"), row.get("AsName")
            if type(asid) is not int or asid <= 0 or not isinstance(name, str) or not name.strip():
                raise ApiError(502, "柠檬云账套缺少有效编号或名称")
            if asid in seen or len(name) > 255:
                raise ApiError(502, "柠檬云账套重复或名称过长")
            seen.add(asid)
            result.append({"asid": str(asid), "name": name})
        return result

    def invoices(self, token, asid, start, end):
        records, seen = [], set()
        deadline = time.monotonic() + 120
        # 不依赖尚未实测的 Count 总数含义；继续至空页，并检测重复页及明确上限。
        for page in range(1, 22):
            if time.monotonic() > deadline:
                raise ApiError(502, "柠檬云拉取时间过长，请缩小日期范围；本次未保存发票")
            data = self._post(
                "/api/Invoice/Invoice/GetInvoice",
                token,
                asid=asid,
                operation="invoices",
                params={
                    "invoiceCategory": 10080,
                    "startDate": start,
                    "endDate": end,
                    # 这些查询键参与上游路由选择；即使不筛选也不能省略，否则返回 404。
                    "number": "",
                    "invoiceType": 0,
                    "name": "",
                    "invoiceStatus": 0,
                    "page": page,
                    "rows": 100,
                },
            )
            rows = data.get("List")
            if not isinstance(rows, list) or len(rows) > 100:
                raise ApiError(502, "柠檬云发票分页格式异常，未保存发票")
            if not rows:
                return records
            if page > 20:
                raise ApiError(422, "本次超过 2000 张发票，请缩小日期范围；本次未保存")
            for row in rows:
                identifier = row.get("InvoiceId") if isinstance(row, dict) else None
                if type(identifier) is not int or identifier <= 0 or identifier in seen:
                    raise ApiError(502, "柠檬云发票编号缺失或分页重复，请重新查询；本次未保存")
                seen.add(identifier)
                records.append(row)
        raise ApiError(502, "柠檬云分页未结束，本次未保存")
