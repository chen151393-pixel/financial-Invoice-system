"""用已保存的 NS 来源定位展示行；不推算报关数量、金额或开票额度。"""

from collections import defaultdict


def value(raw):
    if isinstance(raw, dict):
        raw = raw.get("id")
    return str(raw).strip() if raw is not None else ""


def active(record):
    return record.get("isInactive", record.get("isinactive", False)) in (False, "F", "false", None)


def source_records(source, record_type, identity, line_type):
    if (
        not isinstance(source, dict)
        or source.get("recordType") != record_type
        or value(source.get("recordId")) != value(identity)
        or source.get("lineType") != line_type
    ):
        return {}, {}
    rows = source.get("lines", [])
    if len({value(row.get("id")) for row in rows}) != len(rows):
        return {}, {}
    return source.get("record", {}), {
        f"{line_type}:{value(row.get('id'))}": row["record"]
        for row in rows
        if row.get("id") and isinstance(row.get("record"), dict) and active(row["record"])
    }


def packing_index(evidence, declaration_id):
    """母行使用 NS 原生行号和销售采购行链接核实，不能拿本地自增 ID 代替。"""
    parent_items = {
        (value(row.get("transaction")), value(row.get("id")), value(row.get("item")))
        for row in evidence.get("parentLines", [])
        if row.get("mainline") == "F" and row.get("taxline") == "F" and row.get("item")
    }
    parents_by_sales = defaultdict(set)
    for row in evidence.get("purchaseLinks", []):
        if row.get("nexttype") != "PurchOrd" or row.get("previoustype") != "SalesOrd":
            continue
        parents_by_sales[(value(row.get("previousdoc")), value(row.get("previousline")))].add(
            (value(row.get("nextdoc")), value(row.get("nextline")))
        )
    index = defaultdict(list)
    for row in evidence.get("packingLines", []):
        if not active(row) or value(row.get("custrecord_swc_declare_record")) != declaration_id:
            continue
        parent = value(row.get("custrecord_swc_sublist_protranid"))
        item = value(row.get("custrecord_swc_sublist_itemid"))
        sales = value(row.get("custrecord_swc_sublist_createdfrom"))
        sales_line = value(row.get("custrecord_swc_so_lineid"))
        parent_lines = {
            line
            for purchase, line in parents_by_sales[(sales, sales_line)]
            if purchase == parent and (parent, line, item) in parent_items
        }
        # 同一 Packing 对应多条母采购行时不猜测；无母 PO 走履行请求及销售行引用。
        if parent and len(parent_lines) != 1:
            continue
        key = (
            value(row.get("custrecord_swc_sublist_packingmain")),
            value(row.get("custrecord_swc_sublist_purchaseorderhead")),
            item,
            parent,
            next(iter(parent_lines), ""),
        )
        index[key].append(row)
    return index


def local_line_relations(head, details, purchases, lines, evidence):
    """仅接收唯一的公司＋原报关品名＋Packing 货源地汇总行；不按普通商品名猜配。"""
    if not evidence or evidence.get("mode") not in ("full_sync", "evidence_backfill"):
        return {}
    if evidence.get("mode") == "evidence_backfill":
        synced = head.get("synced_at")
        if not synced or evidence.get("baseSyncedAt") != synced.isoformat():
            return {}
    declaration_id = value(head["ns_internal_id"])
    _, summaries = source_records(
        head.get("source_data"),
        "customrecord_swc_declare_record",
        declaration_id,
        "customrecord_swc_delare_detail",
    )
    summary_index = defaultdict(list)
    for row in details:
        record = summaries.get(row.get("source_line_key"), {})
        if value(record.get("custrecord_swc_relate_record")) != declaration_id:
            continue
        key = (
            value(record.get("custrecord_swc_company")),
            value(record.get("custrecord_swc_delare_name")),
            value(record.get("custrecord_swc_goods_place")),
        )
        if all(key):
            summary_index[key].append(str(row["id"]))
    packing = packing_index(evidence, declaration_id)
    bindings = {}
    for order in purchases:
        record, raw_lines = source_records(
            order.get("source_data"),
            "customrecord_swc_subpo",
            order.get("ns_internal_id"),
            "customrecord_swc_subpo_item",
        )
        if (
            not active(record)
            or value(record.get("custrecord_swc_subpo_baoguannum")) != declaration_id
            or order["ns_account"] != head["ns_account"]
            or order["tenant_id"] != head["tenant_id"]
        ):
            continue
        pl = value(record.get("custrecord_swc_subpo_plnum"))
        company = value(record.get("custrecord_swc_subpo_class"))
        parent = value(record.get("custrecord_swc_subpo_mainpo"))
        sales = value(record.get("custrecord_swc_subpo_so"))
        if not pl or not company:
            continue
        for line in lines:
            if line["purchase_order_id"] != order["id"]:
                continue
            raw = raw_lines.get(line.get("source_line_key"), {})
            if value(raw.get("custrecord_swc_subpo_main")) != value(order.get("ns_internal_id")):
                continue
            item = value(raw.get("custrecord_swc_subpo_item_item"))
            parent_line = value(raw.get("custrecord_swc_subpo_item_mainpo_lineid")) if parent else ""
            fulfillment = value(raw.get("custrecord_swc_subpo_item_ifreqid"))
            sales_line = value(raw.get("custrecord_swc_subpo_item_solineid"))
            # NS 创建脚本由原报关子行复制 bgname，普通采购品名不具有同等来源含义。
            name = value(raw.get("custrecord_swc_subpo_item_bgname"))
            if not item or not name or (parent and not parent_line):
                continue
            if not parent and not all((fulfillment, sales, sales_line)):
                continue
            candidates = [
                pack
                for pack in packing[(pl, company, item, parent, parent_line)]
                if (not fulfillment or value(pack.get("custrecord_swc_sublist_fulreq_tranid")) == fulfillment)
                and (not sales or value(pack.get("custrecord_swc_sublist_createdfrom")) == sales)
                and (not sales_line or value(pack.get("custrecord_swc_so_lineid")) == sales_line)
            ]
            targets = [
                summary_index[(company, name, value(pack.get("custrecord_swc_sublist_purchasesource")))]
                for pack in candidates
            ]
            # 一条子采购汇总行若跨多个报关汇总行，必须保留未定位，不能复制整行金额。
            if targets and all(len(target) == 1 for target in targets):
                unique = {target[0] for target in targets}
                if len(unique) == 1:
                    bindings[str(line["id"])] = next(iter(unique))
    return bindings
