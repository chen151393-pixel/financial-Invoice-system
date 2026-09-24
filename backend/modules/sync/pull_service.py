"""有界分页读取：整页详情成功才返回，不写入 NS 或本地业务库。"""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.core.errors import ApiError

SOURCES = {
    "purchase-orders": ("采购订单", None),
    "sub-purchase-orders": ("子采购订单", "purchase"),
    "customs-declarations": ("报关单", "customs"),
}


def display(value):
    if isinstance(value, dict):
        return str(value.get("refName") or value.get("id") or "")
    return "" if value is None else str(value)


def exact_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: exact_value(item) for key, item in value.items() if key != "links"}
    if isinstance(value, list):
        return [exact_value(item) for item in value]
    return value


class PullService:
    def __init__(self, settings, ns, storage=None):
        self.settings, self.ns, self.storage = settings, ns, storage

    def query_date(self, value):
        # 日期格式取自服务器配置，不能按失败结果盲目换格式重试。
        if self.settings.sync_date_format == "YYYY-MM-DD":
            return value.isoformat()
        if self.settings.sync_date_format == "M/D/YYYY":
            return f"{value.month}/{value.day}/{value.year}"
        if self.settings.sync_date_format == "D/M/YYYY":
            return f"{value.day}/{value.month}/{value.year}"
        raise ApiError(503, "NS 同步日期格式配置无效，请联系管理员")

    def record_type(self, kind):
        section = SOURCES[kind][1]
        mapping = self.settings.pl_lookup.get(section, {}) if section else {}
        value = mapping.get("type", "") if isinstance(mapping, dict) else ""
        record_type = value if section else "purchaseOrder"
        if not record_type:
            raise ApiError(503, "请先配置 NETSUITE_PL_LOOKUP 中对应单据的 type 映射")
        if record_type not in self.settings.record_types:
            raise ApiError(503, f"请在 NETSUITE_RECORD_TYPES 中授权 {record_type} 只读访问")
        self.ns.validate(record_type)
        return record_type

    def sources(self):
        result = []
        storage = (
            self.storage.configuration() if self.storage else {"allowed": False, "reason": "尚未配置业务存储"}
        )
        for kind, (label, _) in SOURCES.items():
            try:
                record_type = self.record_type(kind)
                missing = self.settings.missing()
                allowed = not missing
                reason = (
                    "可按页读取 NS 单据；仅拉取不入库，保存需使用专用操作" if allowed else "NS 连接配置不完整"
                )
            except ApiError as exc:
                record_type, allowed, reason = "", False, exc.message
            result.append(
                {
                    "kind": kind,
                    "label": label,
                    "recordType": record_type,
                    "allowed": allowed,
                    "reason": reason,
                    "storageAllowed": allowed and storage["allowed"] and kind != "purchase-orders",
                    "storageReason": "标准采购订单尚未配置独立存储映射"
                    if kind == "purchase-orders"
                    else storage["reason"],
                }
            )
        return {"sources": result, "lemon": {"allowed": False, "reason": "柠檬云接口尚未接入"}}

    def pull_and_save(self, kind, request, owner):
        if self.storage is None:
            raise ApiError(503, "尚未配置业务存储")
        return self.storage.sync_page(kind, lambda: self.pull(kind, request), owner)

    def pull(self, kind, request):
        record_type = self.record_type(kind)
        if self.settings.missing():
            raise ApiError(503, "NS 连接配置不完整，请联系管理员")
        query_params = {"limit": request.limit, "offset": request.offset}
        if request.startDate:
            start, end = (
                date.fromisoformat(request.startDate),
                date.fromisoformat(request.endDate) + timedelta(days=1),
            )
            field = "createdDate" if kind == "purchase-orders" else "created"
            # 按当前 NS 账户的查询日期格式编码，接口输入始终保持 YYYY-MM-DD。
            query_params["q"] = (
                f'{field} ON_OR_AFTER "{self.query_date(start)}" AND {field} BEFORE "{self.query_date(end)}"'
            )
        data = self.ns.request(
            "GET",
            record_type,
            query_params=query_params,
            exact_numbers=True,
        )["data"]
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ApiError(502, "NS 列表响应不完整")
        items, has_more = data["items"], data.get("hasMore")
        if not isinstance(has_more, bool) or len(items) > request.limit or (has_more and not items):
            raise ApiError(502, "NS 分页响应无效，未返回不完整结果")
        rows, seen = [], set()
        for item in items:
            record_id = str(item.get("id", "")) if isinstance(item, dict) else ""
            if not re.fullmatch(r"[0-9]{1,40}", record_id) or record_id in seen:
                raise ApiError(502, "NS 列表包含无效或重复的内部 ID")
            seen.add(record_id)
            detail = self.ns.request("GET", record_type, record_id, exact_numbers=True)["data"]
            if not isinstance(detail, dict) or str(detail.get("id")) != record_id:
                raise ApiError(502, "NS 单据详情不完整，整页拉取失败")
            rows.append(
                {
                    "id": record_id,
                    "number": display(detail.get("tranId") or detail.get("name") or record_id),
                    "record": exact_value(detail),
                }
            )
        next_offset = request.offset + request.limit
        if has_more and next_offset // request.limit >= 1000:
            raise ApiError(422, "已达到分页查询上限，请联系管理员缩小数据范围")
        return {
            "kind": kind,
            "label": SOURCES[kind][0],
            "recordType": record_type,
            "rows": rows,
            "count": len(rows),
            "offset": request.offset,
            "hasMore": has_more,
            "nextOffset": next_offset if has_more else None,
            "pulledAt": datetime.now(timezone.utc).isoformat(),
            "message": "本页单据读取完成，未写入本地业务库",
            "dateRange": {
                "startDate": request.startDate,
                "endDate": request.endDate,
                "label": "创建日期",
            },
        }
