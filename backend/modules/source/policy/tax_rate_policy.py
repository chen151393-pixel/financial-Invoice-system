"""NS 税码显示名 → 税率小数；只认显示名中的百分数，不按税码 ID 猜测。"""

import re
from decimal import Decimal

_PERCENT = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")


def parse_tax_rate(value):
    """{"id": "920", "refName": "13%"} 或 "VAT_CN:13%" → Decimal("0.13")；无法识别返回 None。"""
    text = value.get("refName") if isinstance(value, dict) else value
    if not isinstance(text, str):
        return None
    found = _PERCENT.findall(text)
    if not found:
        return None
    rate = Decimal(found[-1]) / 100
    return rate if 0 <= rate < 1 else None
