"""只转换已读取的源字段；不猜测同名字段，不进行商品匹配或金额分摊。"""

from decimal import Decimal

from backend.core.errors import ApiError


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


def normalize(value):
    """原始记录转为可存 JSON 的值；数值必须是 Decimal，拒绝可能丢失精度的浮点。"""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ApiError(422, "来源包含非有限数值")
        return str(value)
    if isinstance(value, float):
        raise ApiError(422, "来源小数必须按Decimal读取，未保存可能丢失精度的数据")
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value
