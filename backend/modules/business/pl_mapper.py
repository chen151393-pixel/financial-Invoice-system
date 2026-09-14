"""只转换已读取的源字段；不猜测同名字段，不进行商品匹配或金额分摊。"""

from decimal import Decimal


def text(value):
    if isinstance(value, dict):
        return str(value.get("refName") or value.get("id") or "")
    if value is None:
        return ""
    if isinstance(value, (str, int, float, Decimal)):
        return str(value)
    return ""


def reference(value):
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return ""


def project(record, spec):
    return {key: text(record.get(field)) for key, field in spec.fields.items()}
