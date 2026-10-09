"""发票先核对获批报关行，再核实NS明确关联的本地子采购来源。"""

import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext


def normalize(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or ""))


def remark_matches(remark, number):
    value = normalize(number).upper()
    source = unicodedata.normalize("NFKC", remark or "").upper()
    return (
        bool(value)
        and re.search(r"(?<![A-Z0-9_-])" + re.escape(value) + r"(?![A-Z0-9_-])", source) is not None
    )


def currency(value):
    name = normalize(value).upper()
    return "CNY" if name in {"人民币", "RMB", "CNY"} else name


def number(value, *, positive=False):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or (positive and result <= 0):
            return None
        return result
    except (InvalidOperation, TypeError, ValueError):
        return None


def source_line_ids(source_key, *, purchase):
    """只接受共用NS脚本的原生行ID结构；显示行号不构成来源身份。"""
    try:
        value = json.loads(source_key)
        if not isinstance(value, list) or not value:
            return ()
        if not purchase:
            return (value[0],) if len(value) == 1 and isinstance(value[0], str) and value[0].isdigit() else ()
        if len(value) == 2 and isinstance(value[0], str) and value[0].isdigit() and isinstance(value[1], str):
            return (value[0],)
        if all(isinstance(item, str) and item.startswith("[") for item in value):
            parts = [source_line_ids(item, purchase=True) for item in value]
            if all(parts):
                ids = tuple(identity for part in parts for identity in part)
                return ids if len(ids) == len(set(ids)) else ()
    except (TypeError, ValueError):
        pass
    return ()


def line_checks(invoice, item, customs, order, purchase_row):
    """票面字段只与报关开票口径对照；采购名、价、额不参与相等判断。"""
    name = normalize(item.get("item"))
    name = re.sub(r"^\*[^*]+\*", "", name)
    expected_name = normalize(customs.get("declaration_name"))
    model = normalize(item.get("specification"))
    expected_model = normalize(customs.get("specification"))
    quantity = number(item.get("quantity"), positive=True)
    gross = number(item.get("gross"), positive=True)
    net = number(item.get("net"))
    tax = number(item.get("tax"))
    customs_quantity = number(customs.get("declared_quantity"), positive=True)
    customs_gross = number(customs.get("amount"), positive=True)
    purchase_quantity = number(purchase_row["cells"][11], positive=True)
    checks = [
        ("发票状态和明细", invoice.get("sourceStatus") == "normal" and bool(invoice.get("sourceComplete"))),
        (
            "销售方与子采购供应商",
            bool(normalize(invoice.get("seller")))
            and normalize(invoice.get("seller")) == normalize(order.get("supplier_name")),
        ),
        (
            "购买方与申报公司",
            bool(normalize(invoice.get("buyer")))
            and normalize(invoice.get("buyer")) == normalize(customs.get("company_name")),
        ),
        ("开票品名", bool(name and expected_name and name == expected_name)),
        ("规格型号", not expected_model or bool(model and model == expected_model)),
        (
            "开票单位",
            bool(normalize(item.get("unit")))
            and normalize(item.get("unit")) == normalize(customs.get("declared_unit")),
        ),
        (
            "子采购本次报关单位",
            bool(normalize(purchase_row["cells"][12]))
            and normalize(purchase_row["cells"][12]) == normalize(customs.get("declared_unit")),
        ),
        (
            "币种",
            bool(currency(invoice.get("currency")))
            and currency(invoice.get("currency"))
            == currency(customs.get("currency_code"))
            == currency(order.get("currency_code"))
            == currency(purchase_row.get("currency")),
        ),
        (
            "票面金额与税额",
            quantity is not None
            and gross is not None
            and net is not None
            and tax is not None
            and net + tax == gross,
        ),
        (
            "来源数量金额",
            customs_quantity is not None and customs_gross is not None and purchase_quantity is not None,
        ),
    ]
    return [{"label": label, "matched": bool(ok)} for label, ok in checks]


def prorated_amount(total_amount, total_quantity, used_quantity, new_quantity, used_amount):
    """按发票行原金额累计分摊，末次归入余数，不用两位展示单价相乘。"""
    quantum = Decimal(1).scaleb(min(-2, total_amount.as_tuple().exponent))
    with localcontext() as context:
        context.prec = 64
        cumulative = used_quantity + new_quantity
        target = (
            total_amount
            if cumulative == total_quantity
            else (total_amount * cumulative / total_quantity).quantize(quantum, rounding=ROUND_HALF_UP)
        )
        return target - used_amount


def invoice_item_name(value):
    return re.sub(r"^\*[^*]+\*", "", normalize(value))


def item_matches(item, line):
    return bool(invoice_item_name(item.get("item"))) and invoice_item_name(item.get("item")) == normalize(
        line.get("declaration_name")
    )


def declaration_quantity(line):
    # 报关数量和报关单位必须成对使用；不以母单或子单原始单位补空。
    return (
        number(line.get("declaration_quantity"), positive=True)
        if normalize(line.get("declaration_unit"))
        else None
    )


def compare(invoice, item, order, line):
    invoice_qty = number(item.get("quantity"), positive=True)
    purchase_qty = declaration_quantity(line)
    invoice_gross = number(item.get("gross"), positive=True)
    purchase_gross = number(line.get("amount"), positive=True)
    checks = [
        (
            "销售方与供应商",
            invoice.get("seller"),
            order.get("supplier_name"),
            bool(normalize(invoice.get("seller")))
            and normalize(invoice.get("seller")) == normalize(order.get("supplier_name")),
            None,
        ),
        (
            "报关品名",
            invoice_item_name(item.get("item")),
            line.get("declaration_name"),
            item_matches(item, line),
            None,
        ),
        (
            "报关数量",
            item.get("quantity"),
            line.get("declaration_quantity"),
            invoice_qty is not None and purchase_qty is not None and invoice_qty == purchase_qty,
            format(invoice_qty - purchase_qty, "f")
            if invoice_qty is not None and purchase_qty is not None
            else None,
        ),
        (
            "子采购报关单位",
            item.get("unit"),
            line.get("declaration_unit"),
            bool(normalize(item.get("unit")))
            and normalize(item.get("unit")) == normalize(line.get("declaration_unit")),
            None,
        ),
        (
            "含税单价",
            str(invoice_gross / invoice_qty)
            if invoice_gross is not None and invoice_qty is not None
            else None,
            str(purchase_gross / purchase_qty)
            if purchase_gross is not None and purchase_qty is not None
            else None,
            invoice_gross is not None
            and invoice_qty is not None
            and purchase_gross is not None
            and purchase_qty is not None
            and invoice_gross * purchase_qty == purchase_gross * invoice_qty,
            None,
        ),
        (
            "采购含税金额",
            item.get("gross"),
            line.get("amount"),
            invoice_gross is not None and purchase_gross is not None and invoice_gross == purchase_gross,
            format(invoice_gross - purchase_gross, "f")
            if invoice_gross is not None and purchase_gross is not None
            else None,
        ),
    ]
    return [
        {
            "label": label,
            "invoiceValue": str(left) if left is not None else None,
            "purchaseValue": str(right) if right is not None else None,
            "matched": bool(matched),
            "difference": difference,
        }
        for label, left, right, matched, difference in checks
    ]


def capacity(invoice, item, order, line, allocations, source_hash):
    invoice_qty = number(item.get("quantity"), positive=True)
    purchase_qty = declaration_quantity(line)
    invoice_gross = number(item.get("gross"), positive=True)
    purchase_gross = number(line.get("amount"), positive=True)
    invoice_used = sum(
        (
            number(row.get("quantity")) or Decimal(0)
            for row in allocations
            if row.get("invoice_line_id") == item.get("id")
        ),
        Decimal(0),
    )
    purchase_used = sum(
        (
            number(row.get("quantity")) or Decimal(0)
            for row in allocations
            if str(row.get("purchase_line_id")) == str(line.get("id"))
        ),
        Decimal(0),
    )
    invoice_amount_used = sum(
        (
            number(row.get("gross")) or Decimal(0)
            for row in allocations
            if row.get("invoice_line_id") == item.get("id")
        ),
        Decimal(0),
    )
    purchase_amount_used = sum(
        (
            number(row.get("gross")) or Decimal(0)
            for row in allocations
            if str(row.get("purchase_line_id")) == str(line.get("id"))
        ),
        Decimal(0),
    )
    remaining_invoice = invoice_qty - invoice_used if invoice_qty is not None else Decimal(0)
    remaining_purchase = purchase_qty - purchase_used if purchase_qty is not None else Decimal(0)
    suggested = min(remaining_invoice, remaining_purchase)
    reasons = []
    if invoice.get("sourceStatus") != "normal" or not invoice.get("sourceComplete"):
        reasons.append("发票状态或明细待核实")
    if order.get("detail_sync_status") != "complete":
        reasons.append("子采购明细未完整同步")
    if not normalize(invoice.get("buyer")) or normalize(invoice.get("buyer")) != normalize(
        order.get("company_name")
    ):
        reasons.append("购买方与采购公司未核实一致")
    if not normalize(invoice.get("seller")) or normalize(invoice.get("seller")) != normalize(
        order.get("supplier_name")
    ):
        reasons.append("销售方与子采购供应商主体待核实")
    if not currency(invoice.get("currency")) or currency(invoice.get("currency")) != currency(
        order.get("currency_code")
    ):
        reasons.append("发票与采购币种未核实一致")
    if (
        order.get("parent_currency_code")
        and order.get("currency_code")
        and currency(order["currency_code"]) != currency(order["parent_currency_code"])
    ):
        reasons.append("子采购与母采购币种冲突")
    if not item_matches(item, line):
        reasons.append("报关品名不一致")
    if not normalize(item.get("unit")) or normalize(item.get("unit")) != normalize(
        line.get("declaration_unit")
    ):
        reasons.append("子采购报关单位不一致或缺失")
    if invoice_qty is None or purchase_qty is None or invoice_gross is None or purchase_gross is None:
        reasons.append("数量或含税金额缺失")
    elif invoice_gross * purchase_qty != purchase_gross * invoice_qty:
        reasons.append("按报关数量计算的采购含税金额与发票不一致")
    if any(
        row.get("stale")
        for row in allocations
        if row.get("invoice_line_id") == item.get("id")
        or str(row.get("purchase_line_id")) == str(line.get("id"))
    ):
        reasons.append("已有分配来源发生变化，需复核")
    if (
        suggested <= 0
        or (invoice_gross is not None and invoice_amount_used >= invoice_gross)
        or (purchase_gross is not None and purchase_amount_used >= purchase_gross)
    ):
        reasons.append("发票或子采购明细剩余数量、金额不足")
    return {
        "allowed": not reasons,
        "reason": "；".join(reasons) if reasons else "可人工确认明细分配",
        "invoiceRemaining": str(remaining_invoice),
        "purchaseRemaining": str(remaining_purchase),
        "suggestedQuantity": str(max(suggested, Decimal(0))),
    }
