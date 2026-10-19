"""专业版商品行校验：票头与明细必须同票、同金额，缺少数量单位不得确认匹配。"""

from datetime import date
from decimal import Decimal, InvalidOperation

from backend.core.errors import ApiError

from .lemon_invoice_policy import money


def decimal_value(value, label, precision, scale):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
            raise ValueError
        number = Decimal(value)
        if (
            not number.is_finite()
            or abs(number) >= Decimal(10) ** (precision - scale)
            or number != number.quantize(Decimal(10) ** -scale)
        ):
            raise ValueError
        return number
    except (InvalidOperation, ValueError):
        raise ApiError(422, f"发票明细{label}格式或精度异常，本次未保存") from None


def text_value(row, field, label):
    value = row.get(field)
    if value is not None and not isinstance(value, str):
        raise ApiError(422, f"发票明细{label}必须是文本，本次未保存")
    return value.strip() or None if isinstance(value, str) else None


def validate_identity(raw, detail, values):
    for key, source in (("invoiceId", "InvoiceId"), ("invoiceType", "InvoiceType")):
        if type(detail.get(key)) is not int or detail[key] != raw.get(source):
            raise ApiError(422, "发票明细与列表的来源编号或种类不一致，本次未保存")
    if not isinstance(detail.get("number"), str) or detail["number"] != raw["Number"]:
        raise ApiError(422, "发票明细与列表的票号不一致，本次未保存")
    if detail.get("code") not in (None, "") and not isinstance(detail["code"], str):
        raise ApiError(422, "发票明细的代码必须是文本，本次未保存")
    if (detail.get("code") or "") != (raw.get("Code") or ""):
        raise ApiError(422, "发票明细与列表的代码不一致，本次未保存")
    try:
        issued = detail["invoiceDate"]
        if not isinstance(issued, str) or date.fromisoformat(issued[:10]) != values["date"]:
            raise ValueError
    except (KeyError, ValueError):
        raise ApiError(422, "发票明细与列表的开票日期不一致，本次未保存") from None
    if money(detail, "amount") != values["net"] or money(detail, "tax") != values["tax"]:
        raise ApiError(422, "发票读取期间票头金额变化，请重新拉取；本次未保存")
    for key, source in (("name", "Name"), ("isInvalid", "IsInvalid"), ("businessType", "BusinessType")):
        if key not in detail or source not in raw or detail[key] != raw[source]:
            raise ApiError(422, "发票读取期间供应商、状态或业务类型变化，请重新拉取；本次未保存")
        if key != "name" and (type(detail[key]) is not int or type(raw[source]) is not int):
            raise ApiError(422, "发票明细状态或业务类型格式异常，本次未保存")
    if (detail.get("note") or "") != (raw.get("Note") or ""):
        raise ApiError(422, "发票读取期间备注变化，请重新拉取；本次未保存")


def validate_entry(entry):
    name = text_value(entry, "name", "品名")
    model, unit = text_value(entry, "model", "规格"), text_value(entry, "unit", "单位")
    quantity = decimal_value(entry.get("quality"), "数量", 26, 8)
    net, tax = money(entry, "amount"), money(entry, "tax")
    rate = decimal_value(entry.get("taxRate"), "税率", 9, 4)
    # 官方用百分数表示税率；-100 / -101 分别为免税 / 不征税，原码保留在原始证据中。
    if rate in (Decimal(-100), Decimal(-101)):
        rate = None
    elif rate is not None:
        if not 0 <= rate <= 100:
            raise ApiError(422, "发票明细税率超出范围，本次未保存")
        rate /= 100
    gross = money({"gross": net + tax}, "gross")
    return {
        "item_name": name,
        "specification": model,
        "unit": unit,
        "quantity": quantity,
        "unit_price": None,
        "amount_excluding_tax": net,
        "tax_amount": tax,
        "amount_including_tax": gross,
        "tax_rate": rate,
    }


def validate_details(raw, values):
    if "Detail" not in raw:
        return [], "pending"
    detail = raw["Detail"]
    if not isinstance(detail, dict):
        raise ApiError(422, "发票商品明细结构异常，本次未保存")
    validate_identity(raw, detail, values)
    entries = detail.get("invoiceEntries")
    if not isinstance(entries, list) or len(entries) > 10000 or any(not isinstance(e, dict) for e in entries):
        raise ApiError(422, "发票商品明细行缺失或格式异常，本次未保存")
    if not entries:
        return [], "pending"
    rows = [validate_entry(entry) for entry in entries]
    for key, expected in (("amount_excluding_tax", values["net"]), ("tax_amount", values["tax"])):
        if sum((row[key] for row in rows), Decimal(0)) != expected:
            raise ApiError(422, "发票商品明细合计与票头不一致，本次未保存")
    complete = all(
        row["item_name"]
        and row["unit"]
        and row["quantity"] is not None
        and row["quantity"] > 0
        and row["amount_including_tax"] > 0
        for row in rows
    )
    return rows, "complete" if complete else "pending"
