"""用已保存的 NS 来源定位展示行；不推算报关数量、金额或开票额度。"""

from collections import defaultdict

from .parent_summary_policy import parent_summary_bindings
from .purchase_summary_policy import purchase_summary_bindings

LOCAL_RELATION_VERSION = "parent-summary-quantity-v2"


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


def parent_item_keys(evidence):
    """只接受有效母采购商品行的原生行号；主行、税行不提供商品归属。"""
    return {
        (value(row.get("transaction")), value(row.get("id")), value(row.get("item")))
        for row in evidence.get("parentLines", [])
        if row.get("mainline") == "F" and row.get("taxline") == "F" and row.get("item")
    }


def packing_index(evidence, declaration_id):
    """母行使用 NS 原生行号和销售采购行链接核实，不能拿本地自增 ID 代替。"""
    parent_items = parent_item_keys(evidence)
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


def original_packing_consistent(raw, pack):
    """与 PL pl_trace.rawPackingConsistent 一致，核对原始报关行的来源身份。"""
    if not value(raw.get("plId")) or value(raw.get("plId")) != value(
        pack.get("custrecord_swc_sublist_packingmain")
    ):
        return False
    if value(raw.get("parentPurchaseId")) != value(pack.get("custrecord_swc_sublist_protranid")):
        return False
    explicit = value(raw.get("packingId"))
    if explicit and explicit != value(pack.get("id")):
        return False
    for original, field in (
        ("companyId", "custrecord_swc_sublist_purchaseorderhead"),
        ("itemId", "custrecord_swc_sublist_itemid"),
        ("fulfillmentId", "custrecord_swc_sublist_fulreq_tranid"),
        ("fulfillmentLine", "custrecord_swc_sublist_fulreq_lineid"),
    ):
        left, right = value(raw.get(original)), value(pack.get(field))
        if (left and right and left != right) or (not explicit and not (left and right)):
            return False
    return True


def original_packing_index(evidence, declaration_id):
    """无显式 Packing 引用时只接受完整来源唯一命中，不借用别单或停用来源。"""
    packs = [
        pack
        for pack in evidence.get("packingLines", [])
        if active(pack) and value(pack.get("custrecord_swc_declare_record")) == declaration_id
    ]
    packs_by_id = defaultdict(list)
    for pack in packs:
        packs_by_id[value(pack.get("id"))].append(pack)
    result = defaultdict(list)
    for raw in evidence.get("rawLines", []):
        if not active(raw) or value(raw.get("declarationId")) != declaration_id:
            continue
        candidates = packs_by_id[value(raw["packingId"])] if value(raw.get("packingId")) else packs
        matches = [pack for pack in candidates if original_packing_consistent(raw, pack)]
        if len(matches) == 1:
            result[(value(matches[0].get("id")), value(raw.get("companyId")), value(raw.get("name")))].append(
                raw
            )
    return result


def summary_target(candidates, originals, diagnostics):
    """保留原唯一候选；多候选时仅用创建来源的报关单位 ID 消歧，不按数量或规格猜配。"""
    if len(candidates) <= 1:
        return [identity for identity, _ in candidates]
    if not originals or not all(unit for _, unit in candidates):
        return []
    targets = set()
    resolved = []
    for raw in originals:
        unit = value(raw.get("declarationUnitId"))
        matches = [identity for identity, candidate_unit in candidates if unit and unit == candidate_unit]
        if len(matches) != 1:
            return []
        targets.add(matches[0])
        resolved.append(
            {
                "code": "RAW_SUMMARY_UNIT_CANDIDATE",
                "rawLineId": value(raw.get("id")),
                "originalUnitId": unit,
                "customsLineId": matches[0],
                "message": "按原始报关单位定位到唯一报关明细候选，请核实该汇总行报关单位未被修改。",
            }
        )
    # 一条采购来源跨两条汇总行不能复制整行金额。
    if len(targets) != 1:
        return []
    diagnostics.extend(resolved)
    return list(targets)


def local_line_relations(head, details, purchases, lines, evidence, *, diagnostics=None):
    """先核实 Packing 来源；原始行缺失时用子采购报关单位和整组数量消歧。"""
    diagnostics = diagnostics if diagnostics is not None else []
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
    summary_quantities = {}
    parent_summaries = defaultdict(list)
    blocked_parent_headers = set()
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
            summary_index[key].append((str(row["id"]), value(record.get("custrecord_swc_delare_unit"))))
            summary_quantities[str(row["id"])] = record.get("custrecord_swc_delare_quantity")
        parent_key = (
            value(record.get("custrecord_swc_packing_no")),
            key[0],
            value(record.get("custrecord_swc_purachse_no")),
            value(record.get("custrecord_swc_salesorder_number")),
            key[1],
            value(record.get("custrecord_swc_delare_unit")),
        )
        if all(parent_key[:4]):
            if not all(parent_key[4:]) or not key[2]:
                # 不可忽略字段缺失的汇总行，把剩余候选误当成唯一匹配。
                blocked_parent_headers.add(parent_key[:4])
            else:
                parent_summaries[parent_key].append(
                    (str(row["id"]), record.get("custrecord_swc_delare_quantity"))
                )
    packing = packing_index(evidence, declaration_id)
    originals = (
        original_packing_index(evidence, declaration_id)
        if any(len(candidates) > 1 for candidates in summary_index.values())
        else defaultdict(list)
    )
    bindings = {}
    purchase_groups = defaultdict(list)
    blocked_groups = set()
    # 只补足整个 Packing/原始行来源缺失的情况，不能覆盖已有来源之间的矛盾。
    use_parent_summary = not evidence.get("packingLines") and not evidence.get("rawLines")
    parent_items = parent_item_keys(evidence) if use_parent_summary else set()
    parent_groups = defaultdict(list)
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
        if use_parent_summary and any(
            not all(
                value(raw_lines.get(line.get("source_line_key"), {}).get(field))
                for field in ("custrecord_swc_subpo_item_bgname", "custrecord_swc_subpo_item_bgunit")
            )
            for line in lines
            if line["purchase_order_id"] == order["id"]
        ):
            # 缺失品名或单位的子行无法分组，不允许只用同单剩余明细凑出报关数量。
            blocked_parent_headers.add((pl, company, parent, sales))
        for line in lines:
            if line["purchase_order_id"] != order["id"]:
                continue
            raw = raw_lines.get(line.get("source_line_key"), {})
            belongs_to_order = value(raw.get("custrecord_swc_subpo_main")) == value(
                order.get("ns_internal_id")
            )
            item = value(raw.get("custrecord_swc_subpo_item_item"))
            parent_line = value(raw.get("custrecord_swc_subpo_item_mainpo_lineid")) if parent else ""
            fulfillment = value(raw.get("custrecord_swc_subpo_item_ifreqid"))
            sales_line = value(raw.get("custrecord_swc_subpo_item_solineid"))
            # NS 创建脚本由原报关子行复制 bgname，普通采购品名不具有同等来源含义。
            name = value(raw.get("custrecord_swc_subpo_item_bgname"))
            parent_key = (
                pl,
                company,
                parent,
                sales,
                name,
                value(raw.get("custrecord_swc_subpo_item_bgunit")),
            )
            if use_parent_summary and all(parent_key):
                parent_groups[parent_key].append(
                    (
                        str(line["id"]),
                        raw.get("custrecord_swc_subpo_item_bgqty"),
                        belongs_to_order and (parent, parent_line, item) in parent_items,
                    )
                )
            if not belongs_to_order:
                continue
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
            if not evidence.get("rawLines"):
                keys = {
                    (company, name, value(pack.get("custrecord_swc_sublist_purchasesource")))
                    for pack in candidates
                }
                if len(keys) == 1:
                    key = next(iter(keys))
                    purchase_groups[key].append(
                        (
                            str(line["id"]),
                            value(raw.get("custrecord_swc_subpo_item_bgunit")),
                            raw.get("custrecord_swc_subpo_item_bgqty"),
                        )
                    )
                else:
                    # 跨货源地的整条采购行不能拆开或重复加入两个数量分组。
                    blocked_groups.update(keys)
            targets = [
                summary_target(
                    summary_index[(company, name, value(pack.get("custrecord_swc_sublist_purchasesource")))],
                    originals[(value(pack.get("id")), company, name)],
                    diagnostics,
                )
                for pack in candidates
            ]
            # 一条子采购汇总行若跨多个报关汇总行，必须保留未定位，不能复制整行金额。
            if targets and all(len(target) == 1 for target in targets):
                unique = {target[0] for target in targets}
                if len(unique) == 1:
                    bindings[str(line["id"])] = next(iter(unique))
    bindings.update(
        purchase_summary_bindings(
            purchase_groups, summary_index, summary_quantities, blocked_groups, diagnostics
        )
    )
    bindings.update(
        parent_summary_bindings(parent_summaries, parent_groups, blocked_parent_headers, diagnostics)
    )
    return bindings
