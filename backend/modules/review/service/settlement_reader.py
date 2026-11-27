"""供结汇读取的报关单金额：以海关回执当前版本为准（境外收货人、出口日期、出口合同号、成交总价）。

只读；不判断回款路径与结汇状态，那些规则属于 settlement 模块。
"""

from decimal import Decimal

from ..dao import customs_receipt_dao as dao


def settlement_consignee_names(connection):
    """现存回执名称及其当前格式的写入时间，供结汇初始化客户名称；不含金额、审核状态。"""
    return dao.settlement_consignee_names(connection)


def settlement_declarations(connection, *, numbers=None, consignee="", limit=500):
    """返回 [{receipt_id, revision, declaration_no, ns_declaration_id, consignee, export_date,
    sales_orders, currency, amount, currency_issue}]；多币种或缺总价时 amount 为 None 并给出原因。
    limit 为 None 时返回全部（结汇总账需要完整历史）。"""
    heads = dao.settlement_heads(connection, numbers=numbers, consignee=consignee, limit=limit)
    lines = dao.current_lines(connection, [head["id"] for head in heads])
    result = []
    for head in heads:
        rows = lines.get(head["id"], [])
        currencies = {(row["currency"] or "").strip().upper() for row in rows}
        issue = ""
        if not rows:
            issue = "海关回执没有明细"
        elif len(currencies) != 1 or "" in currencies:
            issue = "海关回执明细币制不一致或缺失"
        elif any(row["deal_total"] is None for row in rows):
            issue = "海关回执明细缺少成交总价"
        amount = None if issue else sum((Decimal(row["deal_total"]) for row in rows), Decimal(0))
        orders = sorted({row["contract_no"].strip() for row in rows if (row["contract_no"] or "").strip()})
        result.append(
            {
                "receipt_id": head["id"],
                "revision": head["revision"],
                "declaration_no": head["declaration_no"],
                "ns_declaration_id": head["ns_declaration_id"],
                "consignee": head["consignee"] or "",
                "export_date": head["export_date"],
                "sales_orders": orders,
                "currency": next(iter(currencies)) if len(currencies) == 1 else "",
                "amount": amount,
                "currency_issue": issue,
            }
        )
    return result


def settlement_declaration_lines(connection, numbers):
    """按报关单号返回海关回执当前版本明细，供结汇生成销售合同：
    {declaration_no: [{item_no, name, specification, contract_no, unit, quantity, currency, total}]}。"""
    heads = dao.settlement_heads(connection, numbers=list(numbers), limit=max(len(numbers), 1))
    lines = dao.current_lines(connection, [head["id"] for head in heads])
    return {
        head["declaration_no"]: [
            {
                "item_no": row["item_no"],
                "name": row["name"],
                "specification": row["specification"],
                "contract_no": row["contract_no"],
                "unit": row["deal_unit"],
                "quantity": row["deal_quantity"],
                "currency": row["currency"],
                "total": row["deal_total"],
            }
            for row in lines.get(head["id"], [])
        ]
        for head in heads
    }
