"""按子采购的母单及原生行引用补充母采购单位，供财务比较口径使用。"""

from collections import defaultdict

from ..policy.local_relation_policy import source_records, value


def _unit_name(row):
    name = str(row.get("unitname") or "").strip()
    if name:
        return name
    # 旧快照只接受已保存的明确名称；母采购 units 编号与报关单位字典不属于同一来源。
    unit = row.get("units")
    if isinstance(unit, dict):
        return str(unit.get("refName") or "").strip()
    if isinstance(unit, str) and not unit.strip().isdigit():
        return unit.strip()
    return ""


def parent_purchase_units(orders, lines, evidence):
    """返回附加母采购单位及缺失原因的明细副本，原始数量、单位和冻结依据保持原值。"""
    parents = defaultdict(list)
    for row in (evidence or {}).get("parentLines", []):
        if row.get("mainline") == "F" and row.get("taxline") == "F" and row.get("item"):
            key = tuple(value(row.get(field)) for field in ("transaction", "id", "item"))
            parents[key].append(row)
    sources = {
        order["id"]: source_records(
            order.get("raw_payload"),
            "customrecord_swc_subpo",
            order["ns_internal_id"],
            "customrecord_swc_subpo_item",
        )
        for order in orders
    }
    result = []
    for line in lines:
        head, records = sources.get(line["purchase_order_id"], ({}, {}))
        parent = value(head.get("custrecord_swc_subpo_mainpo"))
        record = records.get(line["source_line_key"], {})
        line_ref = value(record.get("custrecord_swc_subpo_item_mainpo_lineid"))
        item = value(record.get("custrecord_swc_subpo_item_item"))
        unit = ""
        if not head:
            issue = "子采购原始来源缺失，无法定位母采购明细，请重新同步"
        elif not parent:
            issue = "未关联母采购单，无法核对采购单位"
        elif not line_ref or not item:
            issue = "母采购明细行引用缺失，无法核对采购单位，请重新同步"
        elif len(matches := parents[(parent, line_ref, item)]) != 1:
            issue = "母采购对应明细缺失或不唯一，无法核对采购单位，请重新同步"
        else:
            unit = _unit_name(matches[0])
            issue = "" if unit else "母采购对应明细的采购单位缺失，请重新同步母采购行依据"
        result.append({**line, "parent_purchase_unit": unit, "parent_purchase_unit_issue": issue})
    return result
