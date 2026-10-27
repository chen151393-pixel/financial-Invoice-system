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


def check_categories(checks):
    """比对项 → 不一致的异常分类；checks 为 (key, label, result, invoiceValue)。

    工作台按原始比对项统计时只用这一步；超开与不能通过需要完整分配视图，见 anomalies。
    """
    return list(
        dict.fromkeys(
            CATEGORIES.get(key, label)
            for key, label, result, invoice_value in checks
            if result != "match"
            and not (key == "buyer" and invoice_value is None)
            and not (key == "price" and result == "missing")
        )
    )


def anomalies(view):
    """view：分配视图（AllocationView）；返回异常分类列表，空表示正常。"""
    found = check_categories(
        (check.key, check.label, check.result, check.invoiceValue) for check in view.checks
    )
    if view.exceedsExpected:
        found.append("超开")
    if not view.confirm.allowed:
        found.append("不能通过")
    return list(dict.fromkeys(found))
