"""订阅手动拉票：校验、去重及复用不可变版本；不调用外部系统。"""

from datetime import datetime, timezone

from backend.core.errors import ApiError

from ..dao import header_dao, item_dao, lemon_invoice_dao, raw_record_dao
from ..mapper.lemon_invoice_mapper import prepare
from ..policy.lemon_detail_feedback import detail_feedback
from ..policy.lemon_detail_policy import validate_details
from ..policy.lemon_invoice_policy import validate
from ..policy.lemon_scope_policy import describe_lemon_result
from ..policy.version_policy import digest, projection
from ..public import InvoicesImported, LemonInvoicesStored
from .version_service import save_version


def prepared_batch(event):
    result, seen, ids = [], set(), set()
    for raw in event.records:
        values = validate(raw, event.start, event.end)
        detail_rows, detail_status = validate_details(raw, values)
        item = prepare(raw, values, event.account, detail_rows, detail_status)
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
    if old["source"] != item["header"]["source"] or old["external_id"] != item["header"]["external_id"]:
        raise ApiError(409, "同票来源身份冲突，整批未保存，请核实原记录")
    old_rows = item_dao.by_invoices(connection, [old["id"]])
    if digest(old, old_rows) == digest(item["header"], item["rows"]):
        return "unchanged"
    head, rows = projection(item["header"], item["rows"], old_rows)
    if digest(old, old_rows) == digest(head, rows):
        return "unchanged"
    return "updated"


def on_lemon_invoices_fetched(connection, event, *, events):
    prepared = prepared_batch(event)
    available_types = sorted({item["header"]["business_type"] for item in prepared})
    sources = lemon_invoice_dao.source_keys(
        connection, event.account, [item["header"]["external_id"] for item in prepared]
    )
    existing = header_dao.by_keys(connection, event.account, [item["key"] for item in prepared])
    prepared = selected_batch(prepared, existing, sources, event.business_types)
    keys = [item["key"] for item in prepared]
    if lemon_invoice_dao.excel_conflicts(connection, keys):
        raise ApiError(409, "存在已由 Excel 导入的同票；其账套尚未对齐，整批未保存，避免重复收票")
    counts, changed = save_batch(connection, prepared, existing, event.account, events)
    if changed:
        events.publish(connection, InvoicesImported(tuple(changed)))
    events.publish(
        connection,
        LemonInvoicesStored(
            event.scope,
            event.request_id,
            describe_lemon_result(
                {
                    **counts,
                    "fetched": len(event.records),
                    "excluded": len(event.records) - len(prepared),
                    **detail_counts(connection, event.account, prepared),
                    "businessTypes": list(event.business_types),
                    "availableBusinessTypes": available_types,
                }
            ),
        ),
    )


def detail_counts(connection, account, prepared):
    saved = header_dao.by_keys(connection, account, [item["key"] for item in prepared])
    complete = sum(row["detail_status"] == "complete" for row in saved.values())
    return {
        "completeDetails": complete,
        "pendingDetails": len(saved) - complete,
        **detail_feedback(prepared, saved),
    }


def selected_batch(prepared, existing, sources, business_types):
    selected = []
    for item in prepared:
        external_id = item["header"]["external_id"]
        if sources.get(external_id, item["key"]) != item["key"]:
            raise ApiError(409, "同一来源记录的票号发生变化，整批未保存，请核实")
        if item["header"]["business_type"] in business_types:
            selected.append(item)
        elif external_id in sources:
            old = existing.get(item["key"])
            if old and old["business_type"] != item["header"]["business_type"]:
                # 上游改类型仍须让旧依据失效；仅取消勾选不会修改已保存票据。
                item["header"]["status"] = "unknown"
                selected.append(item)
    return selected


def save_batch(connection, prepared, existing, account, events):
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    changed, now = [], datetime.now(timezone.utc).replace(tzinfo=None)
    for item in prepared:
        action = classify(connection, item, existing.get(item["key"]))
        counts[action] += 1
        if action != "unchanged":
            changed.append(save_version(connection, item, existing.get(item["key"]), events, now))
        else:
            raw_record_dao.save(
                connection,
                {
                    "source": item["header"]["source"],
                    "lemon_account": account,
                    "external_id": item["header"]["external_id"],
                    "payload": item["payload"],
                    "payload_sha256": item["digest"],
                },
                now,
            )
    return counts, changed
