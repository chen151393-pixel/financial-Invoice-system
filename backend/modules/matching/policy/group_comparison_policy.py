"""发票行与所选整张子采购单合计的逐项比对；权重、容差在 comparison_policy 定义。

parts 为 [(子采购行上下文, 分配数量, 含税金额)]，数量与金额是该发票行在这些子采购单上的合计口径。
子采购税额 = 各税率的含税合计 × 税率 ÷（1 + 税率），按税率分组四舍五入到分；缺少税率时不校验。
申报价按所涉报关行（去重）的人民币申报金额合计，与发票行不含税金额比较。
"""

from decimal import ROUND_HALF_UP, Decimal

from .comparison_policy import (
    AMOUNT_TOLERANCE,
    GROUP_WEIGHTS,
    PRICE_TOLERANCE,
    SUPPLIER_NOTE,
    TAX_TOLERANCE,
    _check,
    name_result,
    order_number,
    order_reference,
    purchase_item_match,
    same_unit,
    supplier_result,
)

CENT = Decimal("0.01")
_RANK = {"match": 0, "partial": 1, "missing": 2, "mismatch": 3}


def _worst(results):
    return max(results, key=_RANK.__getitem__) if results else "missing"


def _check_group(key, invoice_value, purchase_value, result, difference=None, note=""):
    return _check(key, invoice_value, purchase_value, result, difference, note, weights=GROUP_WEIGHTS)


def purchase_tax(parts):
    """按税率分组推算子采购税额；任一明细缺税率返回 None。"""
    by_rate = {}
    for line, _, amount in parts:
        if line.get("tax_rate") is None:
            return None
        by_rate[line["tax_rate"]] = by_rate.get(line["tax_rate"], Decimal(0)) + amount
    return sum(
        ((amount * rate / (1 + rate)).quantize(CENT, ROUND_HALF_UP) for rate, amount in by_rate.items()),
        Decimal(0),
    )


def compare_group(invoice, item, item_tax, parts):
    """返回 (checks, confidence)；item 为发票行，item_tax 为该行票面税额（可能为空）。"""
    lines = [line for line, _, _ in parts]
    orders = list(dict.fromkeys(line["order_no"] for line in lines))
    references = [order_reference(invoice["remark"], line) for line in lines]
    quantity = sum((value for _, value, _ in parts), Decimal(0))
    amount = sum((value for _, _, value in parts), Decimal(0))
    suppliers = list(dict.fromkeys(line["supplier_name"] for line in lines))
    companies = list(dict.fromkeys(line["company_name"] for line in lines))
    item_matches = [purchase_item_match(item["item_name"], line) for line in lines]
    names = list(dict.fromkeys(name or "" for name, _ in item_matches))
    units = list(dict.fromkeys(line["unit_name"] for line in lines))
    unit_ok = all(same_unit(item["unit"], unit) for unit in units)
    seller = _worst([supplier_result(invoice["seller_name"], name) for name in suppliers])
    parents = list(
        dict.fromkeys(order_number(line["parent_order_no"]) for line in lines if line.get("parent_order_no"))
    )
    checks = [
        _check_group(
            "order",
            invoice["remark"],
            "、".join(orders) + (f"（母采购单 {'、'.join(parents)}）" if parents else ""),
            "match" if all(references) else "mismatch",
            note=f"整单比对 {len(orders)} 张子采购单"
            + ("" if all(references) else "；部分子采购单未被备注命中"),
        ),
        _check_group(
            "seller",
            invoice["seller_name"],
            "、".join(suppliers),
            seller,
            note="" if seller == "match" else SUPPLIER_NOTE,
        ),
        _check_group(
            "buyer",
            invoice["buyer_name"],
            "、".join(companies),
            _worst(
                [
                    name_result(invoice["buyer_name_normalized"], line["company_name_normalized"])
                    for line in lines
                ]
            ),
            note="" if invoice["buyer_name"] else "发票未提供购买方",
        ),
        _check_group(
            "item",
            item["item_name"],
            "、".join(names),
            _worst([result for _, result in item_matches]),
        ),
        _check_group(
            "unit",
            item["unit"],
            "、".join(units),
            "match" if unit_ok else "mismatch",
            note="" if unit_ok else "发票与子采购单位不同，须核实换算",
        ),
        _check_group(
            "quantity",
            item["quantity"],
            quantity,
            "match"
            if unit_ok and item["quantity"] is not None and item["quantity"] == quantity
            else "mismatch",
            difference=item["quantity"] - quantity if item["quantity"] is not None else None,
            note=f"子采购 {len(lines)} 行剩余应开数量合计",
        ),
        _check_group(
            "amount",
            item["amount_including_tax"],
            amount,
            "match"
            if item["amount_including_tax"] is not None
            and abs(item["amount_including_tax"] - amount) <= AMOUNT_TOLERANCE
            else "mismatch",
            difference=item["amount_including_tax"] - amount
            if item["amount_including_tax"] is not None
            else None,
            note="发票行价税合计对子采购单含税合计",
        ),
        _tax_check(item_tax, purchase_tax(parts), parts),
        _price_check(item, parts),
    ]
    return checks, sum(Decimal(check["score"]) for check in checks)


def _tax_check(item_tax, expected, parts):
    if expected is None:
        return _check_group(
            "tax", item_tax, None, "missing", note="未校验：子采购明细未同步税率，重新同步后校验"
        )
    if item_tax is None:
        return _check_group("tax", None, expected, "missing", note="未校验：发票行缺少税额")
    rates = sorted({line["tax_rate"] for line, _, _ in parts})
    labels = "、".join(f"{format((rate * 100).normalize(), 'f')}%" for rate in rates)
    return _check_group(
        "tax",
        item_tax,
        expected,
        "match" if abs(item_tax - expected) <= TAX_TOLERANCE else "mismatch",
        difference=item_tax - expected,
        note=f"子采购税额按含税合计 × {labels} ÷（1 + 税率）推算，容差 {TAX_TOLERANCE} 元",
    )


def _price_check(item, parts):
    excluding = item.get("amount_excluding_tax")
    declared = {}
    for line, _, _ in parts:
        value = line.get("declared")
        if not value:
            return _check_group("price", None, None, "missing", note="未校验：部分子采购行没有行级报关关联")
        if value["amount_cny"] is None:
            return _check_group("price", None, None, "missing", note=f"未校验：{value['reason']}")
        declared[value["customs_line_id"]] = value["amount_cny"]
    if excluding is None:
        return _check_group("price", None, None, "missing", note="未校验：发票缺少不含税金额")
    total = sum(declared.values(), Decimal(0))
    over = excluding - total > PRICE_TOLERANCE
    return _check_group(
        "price",
        f"不含税 {excluding.quantize(CENT)}",
        f"申报 {total.quantize(CENT)}（{len(declared)} 条报关行合计）",
        "mismatch" if over else "match",
        note=f"不含税总价超出申报价 {(excluding - total).quantize(CENT)}" if over else "",
    )
