"""比对项的展示文字：结果标签与差额说明。

逐行比对中，发票数量／金额不超过子采购剩余应开即判 match（允许分次收票），
此时差额为负，表示收票后仍剩余应开，单写“一致”会被误读为两边数值相同。
展示文字按已保存的比对结果推导，不改变判定、分数和审核规则，也适用于历史建议快照。
"""

from decimal import Decimal, InvalidOperation

from .comparison_policy import AMOUNT_TOLERANCE

RESULT_LABELS = {"match": "一致", "partial": "部分一致", "mismatch": "不一致", "missing": "未提供"}
RECEIPT_KEYS = ("quantity", "amount")


def _decimal(value):
    try:
        return Decimal(value) if value not in (None, "") else None
    except InvalidOperation:
        return None


def _plain(key, value):
    # 金额保留两位小数；数量去掉多余的零
    return f"{abs(value):.2f}" if key == "amount" else format(abs(value).normalize(), "f")


def check_labels(check):
    """返回 (resultLabel, differenceLabel)；差额无法解析时保留原差额文本。"""
    result = check["result"]
    label = RESULT_LABELS[result]
    raw = check.get("difference")
    key = check["key"]
    if key not in RECEIPT_KEYS:
        return label, raw
    difference = _decimal(raw)
    if difference is None:
        return label, raw
    tolerance = AMOUNT_TOLERANCE if key == "amount" else Decimal(0)
    if result == "match" and difference < -tolerance:
        return "分次收票", f"收票后剩余应开 {_plain(key, difference)}"
    if result == "match":
        # 两边相等（含金额容差内）；整单比对与逐行收齐都属此类
        return label, None if difference == 0 else f"差额 {raw}，在 0.01 元容差内"
    if difference > 0:
        return label, f"发票多 {_plain(key, difference)}"
    if difference < 0:
        return label, f"发票少 {_plain(key, difference)}"
    return label, raw
