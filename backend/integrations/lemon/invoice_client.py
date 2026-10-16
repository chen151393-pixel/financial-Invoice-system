"""官方 open2 用户授权、账套及进项票只读协议；令牌仅存在于本次调用中。"""

import json
import time
from decimal import Decimal

import httpx

from backend.core.errors import ApiError


class LemonInvoiceClient:
    def __init__(self, settings, binding_client, client=None):
        self.settings, self.binding = settings, binding_client
        self.client = client or httpx.Client(timeout=20, follow_redirects=False, trust_env=False)

    def close(self):
        self.client.close()

    def _post(self, path, token, *, params=None, asid=None):
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if asid is not None:
            headers["asid"] = asid
        try:
            with self.client.stream(
                "POST", self.settings.lemon_host + path, headers=headers, params=params
            ) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise ApiError(502, "柠檬云单页响应过大，请缩小日期范围")
                    chunks.append(chunk)
                data = json.loads(b"".join(chunks), parse_float=Decimal)
        except (httpx.HTTPError, ValueError):
            raise ApiError(502, "柠檬云读取失败，请核实应用权限、账号授权或网络后再查询") from None
        if not isinstance(data, dict) or data.get("State") != 1000:
            raise ApiError(502, "柠檬云未确认查询成功，请核实账号与接口权限")
        if not isinstance(data.get("Data"), dict):
            raise ApiError(502, "柠檬云返回数据结构异常，未保存发票")
        return data["Data"]

    def user_token(self, mobile):
        data = self._post(
            "/api/OAuth2/Token/GetSpecificUserToken",
            self.binding.app_token(),
            params={"userid": mobile, "isOem": "false"},
        )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise ApiError(502, "柠檬云未返回用户授权，请核实已有绑定")
        return token

    def accounts(self, token):
        data = self._post("/api/Settings/AccountSet/GetAccountSets", token)
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
                params={
                    "invoiceCategory": 10080,
                    "startDate": start,
                    "endDate": end,
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
