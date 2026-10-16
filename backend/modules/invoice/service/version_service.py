"""导入一张发票的新版本：保留逻辑行、原始来源与历史分配的引用。"""

from ..dao import header_dao, item_dao, raw_record_dao, version_dao
from ..mapper import import_mapper
from ..policy import version_policy as rules
from ..public import InvoiceChanged, InvoiceChanging


def save_version(connection, item, existing, events, now):
    document = item["document"]
    raw_id = raw_record_dao.save(
        connection,
        {
            "source": import_mapper.EXCEL_SOURCE,
            "lemon_account": import_mapper.EXCEL_ACCOUNT,
            "external_id": item["key"],
            "payload": item["payload"],
            "payload_sha256": item["digest"],
        },
        now,
    )
    head = import_mapper.header_values(document, raw_id, now)
    rows = import_mapper.item_values(document)
    old_version = None
    if existing:
        invoice_id = existing["id"]
        events.publish(connection, InvoiceChanging((invoice_id,)))
        old_head = header_dao.by_ids(connection, [invoice_id], lock=True)[0]
        old_version = old_head["current_version_id"]
        old_items = item_dao.by_invoices(connection, [invoice_id])
        if not rows:
            head["detail_status"] = "pending"
        elif rules.ambiguous(old_items, rows):
            head["detail_status"] = "failed"
            # 身份不明时保留原逻辑明细及占用；明确作废/红冲仍立即传播。
        else:
            item_dao.replace_projection(connection, invoice_id, rows, rules.identity, now)
            head["detail_status"] = "complete" if rows else "pending"
        version_dao.project(connection, invoice_id, head, now)
    else:
        head["detail_status"] = "complete" if rows else "pending"
        invoice_id = header_dao.insert_header(connection, head, now)
        item_dao.insert_items(connection, invoice_id, rows, now)
    saved = item_dao.by_invoices(connection, [invoice_id])
    version_id = version_dao.append(
        connection,
        {
            "invoice_id": invoice_id,
            "content_sha256": rules.digest(head, saved),
            "raw_record_id": raw_id,
            "source": import_mapper.EXCEL_SOURCE,
            "external_id": item["key"],
            "currency_source": "source_rule",
            "source_rule_version": "lemon_cny_v1",
            "header_snapshot": rules.safe(head),
            "items_snapshot": rules.safe(saved),
        },
        now,
    )
    version_dao.project(connection, invoice_id, {"current_version_id": version_id}, now)
    if old_version is not None:
        events.publish(connection, InvoiceChanged(invoice_id, old_version, version_id, head["status"]))
    return invoice_id
