"""海关回执与 NS 报关单的明细比对规则（纯函数）。

1. 以出口报关单号对应 NS 报关单的真实报关单号；同号多张有效报关单时不比对明细。
2. 同一报关单内，海关项与 NS 报关行各自按“规范化品名 + 规范化单位”归组并合计数量；
   NS 一行可对应海关多项（拆行），NS 多行也可对应海关一项（合并），合计相等即一致。
3. 单位：海关取成交单位，NS 取报关单位（单位字典显示名）；法定单位只展示。
4. 品名相同但单位不同的剩余组配对为“单位不一致”；其余为单边缺失。
5. 数量按十进制精确比较，不设容差；差异需在 NS 修正后重新匹配。
"""

from decimal import Decimal

from backend.core.names import normalize_name

GROUP_LABELS = {
    "matched": "一致",
    "split": "拆行一致",
    "merged": "合并一致",
    "quantity_mismatch": "数量不一致",
    "unit_mismatch": "单位不一致",
    "missing_in_ns": "NS 无对应行",
    "missing_in_customs": "海关无对应项",
}
CONSISTENT = {"matched", "split", "merged"}
STATUS_LABELS = {
    "matched": "一致",
    "split_matched": "拆行一致",
    "different": "有差异",
    "ns_missing": "未找到 NS 报关单",
    "ns_duplicate": "NS 报关单重号",
}


def text(value):
    """十进制数量去掉多余的尾随零，用于展示与 JSON 存储。"""
    if value is None:
        return ""
    normalized = Decimal(value).normalize()
    return format(
        normalized.quantize(Decimal(1)) if normalized == normalized.to_integral() else normalized, "f"
    )


def _total(values):
    return sum((Decimal(v) for v in values if v is not None), Decimal(0))


def _groups(rows, name_key, unit_key):
    groups = {}
    for row in rows:
        key = (normalize_name(row[name_key]), normalize_name(row[unit_key]))
        groups.setdefault(key, []).append(row)
    return groups


def _ns_view(line):
    return {
        "id": line["id"],
        "lineNo": str(line["line_no"] or ""),
        "itemCode": line["item_code"],
        "name": line["name"],
        "specification": line["specification"],
        "quantity": text(line["quantity"]),
        "unit": line["unit"],
    }


def _group(status, ns_lines, items, note):
    return {
        "status": status,
        "label": GROUP_LABELS[status],
        "note": note,
        "nsLines": [_ns_view(line) for line in ns_lines],
        "items": [item["item_no"] for item in items],
    }


def _paired(ns_lines, items):
    ns_qty = _total(line["quantity"] for line in ns_lines)
    customs_qty = _total(item["deal_quantity"] for item in items)
    unit = items[0]["deal_unit"]
    if any(line["quantity"] is None for line in ns_lines):
        return _group("quantity_mismatch", ns_lines, items, "NS 报关数量未提供")
    if ns_qty != customs_qty:
        return _group(
            "quantity_mismatch",
            ns_lines,
            items,
            f"NS {text(ns_qty)} {unit}，海关合计 {text(customs_qty)} {unit}",
        )
    if len(ns_lines) == 1 and len(items) == 1:
        return _group("matched", ns_lines, items, f"数量 {text(ns_qty)} {unit}")
    if len(ns_lines) == 1:
        return _group(
            "split", ns_lines, items, f"NS 1 行 = 海关 {len(items)} 项合计 {text(customs_qty)} {unit}"
        )
    if len(items) == 1:
        return _group(
            "merged", ns_lines, items, f"NS {len(ns_lines)} 行合计 = 海关 1 项 {text(ns_qty)} {unit}"
        )
    return _group(
        "split",
        ns_lines,
        items,
        f"NS {len(ns_lines)} 行 = 海关 {len(items)} 项合计 {text(customs_qty)} {unit}",
    )


def _units(rows, key):
    return "、".join(dict.fromkeys(row[key] or "未提供" for row in rows))


def compare_lines(ns_lines, items):
    """返回比对分组列表；顺序按海关项号，NS 独有行排在最后。"""
    ns_groups = _groups(ns_lines, "name", "unit")
    customs_groups = _groups(items, "name", "deal_unit")
    results = []
    for key in list(customs_groups):
        if key in ns_groups:
            results.append(_paired(ns_groups.pop(key), customs_groups.pop(key)))
    # 剩余同品名不同单位：配对为单位不一致
    leftover_ns = {}
    for (name, _), rows in ns_groups.items():
        leftover_ns.setdefault(name, []).extend(rows)
    for (name, _), rows in customs_groups.items():
        ns_rows = leftover_ns.pop(name, None)
        if ns_rows:
            note = f"NS 单位“{_units(ns_rows, 'unit')}”，海关成交单位“{_units(rows, 'deal_unit')}”"
            results.append(_group("unit_mismatch", ns_rows, rows, note))
        else:
            results.append(_group("missing_in_ns", [], rows, "NS 报关单中没有同名报关行"))
    for rows in leftover_ns.values():
        results.append(_group("missing_in_customs", rows, [], "海关回执中没有同名项"))
    order = {item["item_no"]: index for index, item in enumerate(items)}
    results.sort(key=lambda group: min((order[i] for i in group["items"]), default=len(order)))
    return results


def compare(ns_declarations, items):
    """返回 (状态, NS 报关单 ID 或 None, 比对结果)；ns_declarations 为同号的有效 NS 报关单列表。"""
    if not ns_declarations:
        return "ns_missing", None, {"groups": [], "note": "NS 中没有该真实报关单号的有效报关单"}
    if len(ns_declarations) > 1:
        records = "、".join(d["record_no"] or str(d["id"]) for d in ns_declarations)
        return (
            "ns_duplicate",
            None,
            {"groups": [], "note": f"NS 中有 {len(ns_declarations)} 张报关单使用该单号：{records}"},
        )
    declaration = ns_declarations[0]
    groups = compare_lines(declaration["lines"], items)
    if any(group["status"] not in CONSISTENT for group in groups):
        status = "different"
    elif any(group["status"] != "matched" for group in groups):
        status = "split_matched"
    else:
        status = "matched"
    result = {
        "groups": groups,
        "nsRecordNo": declaration["record_no"],
        "nsLineCount": len(declaration["lines"]),
        "note": "",
    }
    return status, declaration["id"], result
