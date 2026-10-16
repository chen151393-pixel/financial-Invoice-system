"""订阅手动拉票：校验、去重及复用不可变版本；不调用外部系统。"""

from datetime import datetime, timezone

from backend.core.errors import ApiError

from ..dao import header_dao, item_dao, lemon_invoice_dao, raw_record_dao
from ..mapper.lemon_invoice_mapper import prepare
from ..policy.lemon_invoice_policy import BUSINESS_TYPE, validate
from ..policy.version_policy import digest
from ..public import InvoicesImported, LemonInvoicesStored
from .version_service import save_version


def prepared_batch(event):
    result, seen, ids = [], set(), set()
    for raw in event.records:
        values = validate(raw, event.start, event.end)
        item = prepare(raw, values, event.account)
        if item["key"] in seen or raw["InvoiceId"] in ids:
            raise ApiError(422, "本次来源存在重复票号或记录编号，整批未保存")
        seen.add(item["key"])
        ids.add(raw["InvoiceId"])
        result.append(item)
    return result


def classify(connection, item, existing):
    if not existing:
        return "created"
    old = header_dao.by_ids(connection, [existing["id"]])[0]
    if old["source"] != "lemon_open2" or old["external_id"] != item["header"]["external_id"]:
        raise ApiError(409, "同票来源身份冲突，整批未保存，请核实原记录")
    if digest(old, item_dao.by_invoices(connection, [old["id"]])) == digest(item["header"], []):
        return "unchanged"
    return "updated"


def on_lemon_invoices_fetched(connection, event, *, events):
    prepared = prepared_batch(event)
    sources = lemon_invoice_dao.source_keys(
        connection, event.account, [item["header"]["external_id"] for item in prepared]
    )
    prepared = [
        item
        for item in prepared
        if item["header"]["business_type"] == BUSINESS_TYPE or item["header"]["external_id"] in sources
    ]
    for item in prepared:
        if item["header"]["business_type"] != BUSINESS_TYPE:
            item["header"]["status"] = "unknown"
    keys = [item["key"] for item in prepared]
    if lemon_invoice_dao.excel_conflicts(connection, keys):
        raise ApiError(409, "存在已由 Excel 导入的同票；其账套尚未对齐，整批未保存，避免重复收票")
    existing = header_dao.by_keys(connection, event.account, keys)
    counts, changed = save_batch(connection, prepared, existing, sources, event.account, events)
    if changed:
        events.publish(connection, InvoicesImported(tuple(changed)))
    events.publish(
        connection,
        LemonInvoicesStored(
            event.scope,
            event.request_id,
            {
                **counts,
                "fetched": len(event.records),
                "excluded": len(event.records) - len(prepared),
                "pendingDetails": len(prepared),
                "saved": True,
                "message": "拉取结果已提交；商品明细待补齐，暂不生成逐行匹配建议。",
            },
        ),
    )


def save_batch(connection, prepared, existing, sources, account, events):
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    changed, now = [], datetime.now(timezone.utc).replace(tzinfo=None)
    for item in prepared:
        if sources.get(item["header"]["external_id"], item["key"]) != item["key"]:
            raise ApiError(409, "同一来源记录的票号发生变化，整批未保存，请核实")
        action = classify(connection, item, existing.get(item["key"]))
        counts[action] += 1
        if action != "unchanged":
            changed.append(save_version(connection, item, existing.get(item["key"]), events, now))
        else:
            raw_record_dao.save(
                connection,
                {
                    "source": "lemon_open2",
                    "lemon_account": account,
                    "external_id": item["header"]["external_id"],
                    "payload": item["payload"],
                    "payload_sha256": item["digest"],
                },
                now,
            )
    return counts, changed
