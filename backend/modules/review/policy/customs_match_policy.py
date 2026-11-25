"""海关回执与 NS 报关单的明细比对规则（纯函数）。

1. 以出口报关单号对应 NS 报关单的真实报关单号；同号多张有效报关单时不比对明细。
2. 同一报关单内，先按“规范化品名 + 规范化单位”归组，再按两侧唯一且相等的数量逐行配对。
   剩余行保留原有拆行、合并比对，比较数量合计。
3. 单位：海关取成交单位，NS 取报关单位（单位字典显示名）；法定单位只展示。
4. 品名相同但单位不同的剩余组配对为“单位不一致”；其余为单边缺失。
5. 数量按十进制精确比较，不设容差；差异需在 NS 修正后重新匹配。
6. 总价只在一对一行之间比较（同币种、两侧金额齐全），按十进制精确比较；数量一致但总价不同的
   一对一行判为“总价不一致”，报关单整体为有差异。
7. 自动审核（auto_review）只放行逐行一一对应、数量一致且每行总价都已比对一致的报关单；
   拆行、合并或总价未能比对的报关单转人工核实。
"""

from collections import defaultdict
from decimal import Decimal

from backend.core.names import normalize_name

GROUP_LABELS = {
    "matched": "一致",
    "total_mismatch": "总价不一致",
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
# 差异类型（回执头上的标记列）→ 归入该类的分组状态；一张回执可同时属于多类。
DIFFERENCE_KINDS = {
    "quantity_mismatch": ("quantity_mismatch",),
    "unit_mismatch": ("unit_mismatch",),
    "total_mismatch": ("total_mismatch",),
    "line_missing": ("missing_in_ns", "missing_in_customs"),
}


def difference_kinds(result):
    """由比对结果派生四类差异标记；未找到或重号的 NS 报关单没有分组，全部为 False。"""
    statuses = {group["status"] for group in (result or {}).get("groups", [])}
    return {kind: bool(statuses.intersection(groups)) for kind, groups in DIFFERENCE_KINDS.items()}


def text(value):
    """十进制数量去掉多余的尾随零，用于展示与 JSON 存储。"""
    if value is None:
        return ""
    normalized = Decimal(value).normalize()
    return format(
        normalized.quantize(Decimal(1)) if normalized == normalized.to_integral() else normalized, "f"
    )


def amount_text(value):
    """总价展示至少两位小数，保留来源中的有效精度。"""
    if value is None:
        return ""
    integer, _, fraction = text(value).partition(".")
    return f"{integer}.{fraction.ljust(2, '0')}"


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
        "currency": line.get("currency") or "",
        "total": amount_text(line.get("amount")),
    }


def _group(status, ns_lines, items, note):
    return {
        "status": status,
        "label": GROUP_LABELS[status],
        "note": note,
        "nsLines": [_ns_view(line) for line in ns_lines],
        "items": [item["item_no"] for item in items],
        "totalMismatch": _total_mismatch(ns_lines, items)
        if status in {"matched", "total_mismatch", "quantity_mismatch"}
        else None,
    }


def _total_mismatch(ns_lines, items):
    if len(ns_lines) != 1 or len(items) != 1:
        return None
    line, item = ns_lines[0], items[0]
    ns_amount, customs_amount = line.get("amount"), item.get("deal_total")
    currency = (line.get("currency") or "").strip().upper()
    comparable = (
        len(currency) == 3
        and currency.isascii()
        and currency.isalpha()
        and currency == (item.get("currency") or "").strip().upper()
        and ns_amount is not None
        and customs_amount is not None
    )
    return Decimal(ns_amount) != Decimal(customs_amount) if comparable else None


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
        if _total_mismatch(ns_lines, items):
            line, item = ns_lines[0], items[0]
            currency = (line.get("currency") or "").strip().upper()
            return _group(
                "total_mismatch",
                ns_lines,
                items,
                f"数量 {text(ns_qty)} {unit} 一致；总价 NS {currency} {amount_text(line['amount'])}，"
                f"海关 {currency} {amount_text(item['deal_total'])}",
            )
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


def _by_quantity(rows, key):
    groups = defaultdict(list)
    for row in rows:
        if row[key] is not None:
            groups[Decimal(row[key])].append(row)
    return groups


def _match_quantities(ns_lines, items):
    """只有相同数量在两侧各出现一次，才能据此定位具体报关行。"""
    if len(ns_lines) == 1 or len(items) == 1:
        return [_paired(ns_lines, items)]
    ns_quantities = _by_quantity(ns_lines, "quantity")
    item_quantities = _by_quantity(items, "deal_quantity")
    pairs = [
        (ns_quantities[qty], same_qty)
        for qty, same_qty in item_quantities.items()
        if len(same_qty) == 1 and qty in ns_quantities and len(ns_quantities[qty]) == 1
    ]
    if not pairs:
        return [_paired(ns_lines, items)]

    ns_ids = {lines[0]["id"] for lines, _ in pairs}
    item_numbers = {lines[0]["item_no"] for _, lines in pairs}
    ns_remaining = [line for line in ns_lines if line["id"] not in ns_ids]
    items_remaining = [item for item in items if item["item_no"] not in item_numbers]
    # 若扣除相同数量后余项只在一侧，保留完整组以展示拆分数量或原有数量差异。
    if bool(ns_remaining) != bool(items_remaining):
        return [_paired(ns_lines, items)]

    matches = [_paired(lines, matched_items) for lines, matched_items in pairs]
    if ns_remaining:
        matches.append(_paired(ns_remaining, items_remaining))
    return matches


def compare_lines(ns_lines, items):
    """返回比对分组列表；顺序按海关项号，NS 独有行排在最后。"""
    ns_groups = _groups(ns_lines, "name", "unit")
    customs_groups = _groups(items, "name", "deal_unit")
    results = []
    for key in list(customs_groups):
        if key in ns_groups:
            results.extend(_match_quantities(ns_groups.pop(key), customs_groups.pop(key)))
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


AUTO_RULE = "仅逐行一一对应、数量一致且每行总价比对一致的回执可自动审核"


def auto_review(status, result):
    """返回 (是否可自动审核, 转人工原因)；拆行、合并、总价有差异或未能比对的均须人工核实。"""
    if status == "split_matched":
        return False, "NS 报关行与海关项非一一对应（拆行或合并），需人工核实"
    if status == "different":
        return False, "明细或总价有差异，需人工核实"
    if status != "matched":
        return False, ""
    unverified = [
        "、".join(group["items"]) for group in result.get("groups", []) if group["totalMismatch"] is not False
    ]
    if unverified:
        return False, f"海关项 {'、'.join(unverified)} 总价未能比对（币种或金额缺失），需人工核实"
    return True, ""


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
