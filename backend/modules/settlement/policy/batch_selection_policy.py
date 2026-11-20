"""香港建批次选单规则；预核对与事务内提交共用，不读写数据库。"""

from decimal import Decimal

from backend.core.errors import ApiError
from backend.core.names import normalize_name


def _single(values, label):
    distinct = {value for value in values}
    if len(distinct) != 1:
        raise ApiError(422, f"批次内报关单的{label}必须一致，当前有：{'、'.join(sorted(distinct))}")
    return distinct.pop()


def validate_selection(rows, numbers):
    """建批次前的业务校验；返回 (路径, 境外收货人, 币种, 报关合计)。"""
    found = {row["declaration_no"]: row for row in rows}
    missing = [number for number in numbers if number not in found]
    if missing:
        raise ApiError(422, f"以下报关单没有可用的海关回执：{'、'.join(missing)}")
    blocked = [f"{number}（{found[number]['blocked']}）" for number in numbers if found[number]["blocked"]]
    if blocked:
        raise ApiError(409, "以下报关单不能结汇：" + "；".join(blocked))
    chosen = [found[number] for number in numbers]
    ledger = [row["declaration_no"] for row in chosen if row["handling"] != "batch"]
    if ledger:
        raise ApiError(422, "直接收汇的报关单不建批次，请在“直接收汇明细”核对：" + "、".join(ledger))
    route = _single((row["route"] for row in chosen), "回款路径")
    _single((normalize_name(row["consignee"]) for row in chosen), "境外收货人")
    currency = _single((row["currency"] for row in chosen), "币种")
    total = sum((row["amount"] for row in chosen), Decimal(0))
    return route, chosen[0]["consignee"], currency, total
