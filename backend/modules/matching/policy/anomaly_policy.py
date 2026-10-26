"""比对建议异常分类（"只看异常"），纯函数。

异常 = 需要填写说明才能通过，或当前不能通过；分类取自不一致的比对项，不能通过时另记"不能通过"。
购买方未提供、申报价未校验属于数据缺失，不算异常（与填写说明规则一致）。
"""

CATEGORIES = {
    "price": "价格",
    "quantity": "数量",
    "unit": "单位",
    "amount": "金额",
    "item": "品名",
    "seller": "供应商",
    "order": "子采购单号",
    "buyer": "购买方",
}


def anomalies(view):
    """view：分配视图（AllocationView）；返回异常分类列表，空表示正常。"""
    found = [
        CATEGORIES.get(check.key, check.label)
        for check in view.checks
        if check.result != "match"
        and not (check.key == "buyer" and check.invoiceValue is None)
        and not (check.key == "price" and check.result == "missing")
    ]
    if view.exceedsExpected:
        found.append("超开")
    if not view.confirm.allowed:
        found.append("不能通过")
    return list(dict.fromkeys(found))
