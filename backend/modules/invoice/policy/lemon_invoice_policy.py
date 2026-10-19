"""open2 进项票范围、状态和金额校验；缺少商品行时不补造。"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from backend.core.errors import ApiError


def money(raw, field):
    value = raw.get(field)
    if value is None or isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise ApiError(422, f"发票金额字段 {field} 缺失或格式异常")
    try:
        amount = Decimal(value)
        if (
            not amount.is_finite()
            or abs(amount) >= Decimal("1e16")
            or amount != amount.quantize(Decimal("0.01"))
        ):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise ApiError(422, f"发票金额字段 {field} 超出范围或不是两位小数") from None
    return amount


def validate(raw, start, end):
    if raw.get("InvoiceCategory") != 10080:
        raise ApiError(422, "上游返回非进项发票，本次未保存")
    if type(raw.get("InvoiceId")) is not int or raw["InvoiceId"] <= 0:
        raise ApiError(422, "发票缺少稳定来源编号")
    number = raw.get("Number")
    if not isinstance(number, str) or not re.fullmatch(r"[0-9]{1,100}", number):
        raise ApiError(422, "发票号码必须是文本数字，不能将数值转换后保存")
    for field in ("Code", "InvoiceTypeText", "Name", "TaxpayerNumber", "Note"):
        if raw.get(field) is not None and not isinstance(raw[field], str):
            raise ApiError(422, f"发票字段 {field} 格式异常")
    business = raw.get("BusinessTypeText")
    if not isinstance(business, str) or not business.strip():
        raise ApiError(422, "发票缺少业务类型，不能判断导入范围")
    value = raw.get("InvoiceDateText") or raw.get("InvoiceDate")
    try:
        if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}(?:$|T| )", value):
            raise ValueError
        issued = date.fromisoformat(value[:10])
    except ValueError:
        raise ApiError(422, "发票开票日期格式异常") from None
    if not start <= issued <= end:
        raise ApiError(422, "上游返回日期范围外的发票，本次未保存")
    net, tax, gross = (money(raw, key) for key in ("Amount", "Tax", "AdValoremTaxTotals"))
    if net + tax != gross:
        raise ApiError(422, "发票未税额与税额之和不等于价税合计，本次未保存")
    invalid = raw.get("IsInvalid")
    status = (
        {0: "normal", 1: "void", 2: "red_offset"}.get(invalid, "unknown")
        if type(invalid) is int
        else "unknown"
    )
    # 负票不能当作普通蓝票生成建议；部分红冲和未知状态保留为待核实。
    if status == "normal" and gross < 0:
        status = "red_offset"
    return {
        "date": issued,
        "net": net,
        "tax": tax,
        "gross": gross,
        "status": status,
        "business": business.strip(),
    }
