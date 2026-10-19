"""专业版官方网页 GET /api/Invoice 明细协议；只读且不复用其他账套上下文。"""

import time

from backend.core.errors import ApiError

from .professional_accounts import PRO_HOST


class LemonProfessionalInvoiceDetails:
    def __init__(self, accounts):
        self.accounts = accounts

    def enrich(self, token, asid, records, selected_ids):
        if not selected_ids:
            return records
        deadline = time.monotonic() + 120
        with self.accounts.open(token) as (session, context, accounts):
            chosen = next((row for row in accounts or [] if row["asid"] == asid), None)
            if chosen is None:
                raise ApiError(403, "当前账号已无该专业版账套访问权限，本次未保存")
            appasid = chosen["appasid"]
            if not isinstance(appasid, str) or not appasid or len(appasid) > 2048:
                raise ApiError(502, "柠檬云未返回所选专业版账套上下文，本次未保存")
            params = {"serviceId": context["serviceId"], "appasid": appasid}
            result = []
            for row in records:
                if row["InvoiceId"] not in selected_ids:
                    result.append(row)
                    continue
                if time.monotonic() > deadline:
                    raise ApiError(502, "柠檬云明细读取时间过长，请缩小日期范围；本次未保存")
                result.append({**row, "Detail": self._read(session, params, row)})
            return result

    def _read(self, session, params, row):
        invoice_type = row.get("InvoiceType")
        if type(invoice_type) is not int or invoice_type <= 0:
            raise ApiError(502, "柠檬云发票缺少有效种类，无法读取商品明细；本次未保存")
        payload = self.accounts.request(
            session,
            PRO_HOST + "/api/Invoice",
            "invoice_detail",
            params={**params, "invoiceId": row["InvoiceId"], "invoiceType": invoice_type},
            headers={"appasid": params["appasid"]},
        )
        data = payload.get("data")
        if payload.get("state") != 1000 or not isinstance(data, dict):
            raise ApiError(502, "柠檬云未确认商品明细查询成功，本次未保存")
        detail = data.get("invoiceData")
        if not isinstance(detail, dict):
            raise ApiError(502, "柠檬云商品明细响应缺少发票数据，本次未保存")
        entries = detail.get("invoiceEntries")
        if not isinstance(entries, list) or len(entries) > 10000:
            raise ApiError(502, "柠檬云商品明细缺失或超过单票一万行上限，本次未保存")
        if any(not isinstance(entry, dict) for entry in entries):
            raise ApiError(502, "柠檬云商品明细行格式异常，本次未保存")
        # 保留官方原始字段，业务金额、身份及完整性由 invoice 模块统一校验。
        return detail
