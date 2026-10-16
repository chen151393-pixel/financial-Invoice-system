"""发票行与子采购行比对、置信度（数据库设计第 5.1、5.2 节）。权重、分档、容差只在这里定义。

不一致项只降低置信度；是否允许人工通过见 allocation_policy.py。
"""

import re
import unicodedata
from decimal import Decimal

from backend.core.names import normalize_name

WEIGHTS = {"order": 15, "seller": 15, "buyer": 10, "item": 15, "unit": 15, "quantity": 15, "amount": 15}
LABELS = {
    "order": "子采购单号",
    "seller": "销售方与供应商",
    "buyer": "购买方与采购公司",
    "item": "品名",
    "unit": "单位",
    "quantity": "数量",
    "amount": "含税金额",
}
HIGH, MEDIUM = Decimal(80), Decimal(50)
AMOUNT_TOLERANCE = Decimal("0.01")
# 发票品名开头的税收分类，例如 "*计算机设备*服务器"
_TAX_PREFIX = re.compile(r"^\*[^*]*\*")


def tier(confidence):
    if confidence is None:
        return "manual"
    return "high" if confidence >= HIGH else "medium" if confidence >= MEDIUM else "low"


def text(value):
    if value is None:
        return None
    return format(value.normalize(), "f") if isinstance(value, Decimal) else str(value)


def item_name(value):
    return normalize_name(_TAX_PREFIX.sub("", value or ""))


def name_result(invoice_name, purchase_name):
    if not invoice_name or not purchase_name:
        return "missing"
    if invoice_name == purchase_name:
        return "match"
    return "partial" if invoice_name in purchase_name or purchase_name in invoice_name else "mismatch"


def order_in_remark(remark, order_no):
    """备注中出现完整的子采购单号（PO100 不匹配 PO1001）。"""
    if not remark or not order_no:
        return False
    haystack = unicodedata.normalize("NFKC", remark).upper()
    needle = re.escape(unicodedata.normalize("NFKC", order_no).upper())
    return re.search(rf"(?<![A-Z0-9]){needle}(?![A-Z0-9])", haystack) is not None


def _check(key, invoice_value, purchase_value, result, difference=None, note=""):
    weight = WEIGHTS[key]
    score = weight if result == "match" else Decimal(weight) / 2 if result == "partial" else 0
    return {
        "key": key,
        "label": LABELS[key],
        "invoiceValue": text(invoice_value),
        "purchaseValue": text(purchase_value),
        "result": result,
        "difference": text(difference),
        "note": note,
        "score": text(Decimal(score)),
    }


def compare(invoice, item, line, remaining_quantity, remaining_amount):
    """invoice、item 来自 invoice 门面；line 为子采购行上下文。返回 (checks, confidence)。"""
    purchase_item = line["declaration_name"] or line["item_name"]
    unit_match = bool(
        item["unit"] and line["unit"] and normalize_name(item["unit"]) == normalize_name(line["unit"])
    )
    checks = [
        _check(
            "order",
            invoice["remark"],
            line["order_no"],
            "match" if order_in_remark(invoice["remark"], line["order_no"]) else "mismatch",
            note="" if invoice["remark"] else "发票没有备注",
        ),
        _check(
            "seller",
            invoice["seller_name"],
            line["supplier_name"],
            name_result(invoice["seller_name_normalized"], line["supplier_name_normalized"]),
        ),
        _check(
            "buyer",
            invoice["buyer_name"],
            line["company_name"],
            name_result(invoice["buyer_name_normalized"], line["company_name_normalized"]),
            note="" if invoice["buyer_name"] else "发票未提供购买方",
        ),
        _check(
            "item",
            item["item_name"],
            purchase_item,
            name_result(item_name(item["item_name"]), item_name(purchase_item)),
        ),
        _check(
            "unit",
            item["unit"],
            line["unit"],
            "match" if unit_match else "mismatch",
            note="" if line["unit"] else "子采购单位缺失",
        ),
    ]
    checks.extend(_receipt_checks(item, unit_match, remaining_quantity, remaining_amount))
    return checks, sum(Decimal(check["score"]) for check in checks)


def _receipt_checks(item, unit_match, remaining_quantity, remaining_amount):
    quantity, amount = item["quantity"], item["amount_including_tax"]
    amount_gap = amount - remaining_amount if amount is not None and remaining_amount is not None else None
    return [
        _check(
            "quantity",
            quantity,
            remaining_quantity,
            "match"
            if quantity is not None
            and remaining_quantity is not None
            and unit_match
            and 0 < quantity <= remaining_quantity
            else "mismatch",
            difference=quantity - remaining_quantity
            if quantity is not None and remaining_quantity is not None
            else None,
            note="本次数量在剩余应开范围内可分次收票；不同单位须核实换算",
        ),
        _check(
            "amount",
            amount,
            remaining_amount,
            "match"
            if amount_gap is not None and amount > 0 and amount_gap <= AMOUNT_TOLERANCE
            else "mismatch",
            difference=amount_gap,
            note="本次含税金额在剩余额度内可分次收票；收齐容差 0.01 元",
        ),
    ]
