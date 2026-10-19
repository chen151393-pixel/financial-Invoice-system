"""专业版进项票只读分页协议；合计行不作为发票，完整读取后才交给业务层。"""

import logging
import time

from backend.core.errors import ApiError

from .professional_accounts import PRO_HOST

logger = logging.getLogger("ns_api.lemon")
PAGE_SIZE = 100
MAX_INVOICES = 2000


def invoice_rows(data):
    rows = data.get("data")
    total = data.get("count")
    if type(total) is not int or total < 0 or not isinstance(rows, list):
        raise ApiError(502, "柠檬云专业版发票分页格式异常，本次未保存")
    if total > MAX_INVOICES:
        raise ApiError(422, "本次超过 2000 张发票，请缩小日期范围；本次未保存")
    if len(rows) > PAGE_SIZE + 1 or any(not isinstance(row, dict) for row in rows):
        raise ApiError(502, "柠檬云专业版发票分页行数或格式异常，本次未保存")
    # 真实接口在每页末尾返回合计；终止页也可能只有合计。不能泛化跳过缺编号行。
    if rows and is_summary(rows[-1]):
        rows = rows[:-1]
    if len(rows) > PAGE_SIZE:
        raise ApiError(502, "柠檬云专业版发票分页超过单页上限，本次未保存")
    return rows, total


def is_summary(row):
    return (
        type(row.get("invoiceId")) is int
        and row["invoiceId"] == 0
        and type(row.get("invoiceCategory")) is int
        and row["invoiceCategory"] == 0
        and row.get("businessTypeText") == "合计"
        and row.get("number") == ""
        and row.get("code") == ""
        and row.get("invoiceDate") is None
        and row.get("invoiceDateText") == ""
    )


class LemonProfessionalInvoices:
    def __init__(self, accounts):
        self.accounts = accounts

    def query(self, token, asid, start, end):
        with self.accounts.open(token) as (session, context, accounts):
            chosen = next((row for row in accounts or [] if row["asid"] == asid), None)
            if chosen is None:
                raise ApiError(403, "当前账号已无该专业版账套访问权限，本次未保存")
            appasid = chosen["appasid"]
            if not isinstance(appasid, str) or not appasid or len(appasid) > 2048:
                raise ApiError(502, "柠檬云未返回所选专业版账套上下文，本次未保存")
            # 必须使用所选账套的加密上下文，不能复用服务入口的默认账套。
            params = {"serviceId": context["serviceId"], "appasid": appasid, "pageSize": PAGE_SIZE}
            return self._pages(session, params, start, end)

    def _pages(self, session, params, start, end):
        records, seen, total = [], set(), None
        deadline = time.monotonic() + 120
        for page in range(1, MAX_INVOICES // PAGE_SIZE + 2):
            if time.monotonic() > deadline:
                raise ApiError(502, "柠檬云拉取时间过长，请缩小日期范围；本次未保存发票")
            data = self._page(session, {**params, "pageIndex": page}, start, end)
            rows, count = invoice_rows(data)
            if total is not None and total != count:
                raise ApiError(502, "柠檬云专业版发票总数在分页期间变化，请重新查询；本次未保存")
            total = count
            expected = min(PAGE_SIZE, max(0, total - len(records)))
            if len(rows) != expected:
                raise ApiError(502, "柠檬云专业版发票分页与总数不一致，本次未保存")
            if not rows:
                logger.info("lemon_invoices_read source=professional count=%s pages=%s", total, page)
                return records
            for row in rows:
                identifier = row.get("invoiceId")
                if type(identifier) is not int or identifier <= 0 or identifier in seen:
                    raise ApiError(502, "柠檬云专业版发票编号缺失或分页重复，本次未保存")
                seen.add(identifier)
                # 两版同义字段仅大小写不同；金额保留 Decimal，全部业务校验由 invoice 执行。
                canonical = {key[:1].upper() + key[1:]: value for key, value in row.items()}
                if len(canonical) != len(row):
                    raise ApiError(502, "柠檬云专业版发票字段重复，本次未保存")
                records.append(canonical)
        raise ApiError(502, "柠檬云专业版发票分页未结束，本次未保存")

    def _page(self, session, params, start, end):
        payload = self.accounts.request(
            session,
            PRO_HOST + "/api/Invoice/PurchasePagingList",
            "invoices",
            params=params,
            headers={"appasid": params["appasid"]},
            body={
                "startDate": start,
                "endDate": end,
                "invoiceStatus": "0",
                "invoiceType": "0",
                "invoiceVoucherStatus": "0",
                "invoiceIssueDateStatus": "0",
                "invoiceBillStatus": "0",
            },
        )
        if payload.get("state") != 1000 or not isinstance(payload.get("data"), dict):
            raise ApiError(502, "柠檬云未确认专业版进项发票查询成功，本次未保存")
        return payload["data"]
