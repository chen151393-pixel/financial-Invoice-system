"""子采购行对应报关行的人民币申报价（经 public.py 暴露给 matching），需传入调用方的数据库连接。"""

from ..dao import customs_purchase_link_dao, purchase_order_dao, sales_order_dao
from ..dao.unit_dictionary_dao import unit_names
from ..policy.declared_price_policy import declared_cny, pick_sales_order
from ..policy.unit_policy import unit_label


def declared_prices(connection, purchase_line_ids):
    """{子采购行 ID: {customs_line_id, unit, quantity, amount_cny, unit_price_cny, reason}}；
    没有行级报关关联的子采购行不返回。"""
    rows = customs_purchase_link_dao.declared_lines(connection, sorted(set(purchase_line_ids)))
    if not rows:
        return {}
    by_customs = {}
    for row in rows:
        by_customs.setdefault(row["customs_line_id"], []).append(row)
    orders = purchase_order_dao.sales_order_ids(
        connection, sorted({row["purchase_order_id"] for row in rows})
    )
    sales = sales_order_dao.by_ids(connection, [value for value in orders.values() if value])
    names = unit_names(connection)
    result = {}
    for customs_line_id, own in by_customs.items():
        head = own[0]
        candidates = [sales.get(orders.get(row["purchase_order_id"])) for row in own]
        sales_order, sales_reason = pick_sales_order(head["sales_order_no"], candidates)
        # 单价校验按报关数量、报关单位和申报单价（与 NS 报关单打印口径一致），不用 custrecord_swc_unitprice。
        amount, unit_price, reason = declared_cny(
            head["amount"], head["declared_unit_price"], head["currency"], sales_order, sales_reason
        )
        for row in own:
            result[row["purchase_line_id"]] = {
                "customs_line_id": customs_line_id,
                "unit": unit_label(head["declared_unit"], names),
                "quantity": head["declared_quantity"],
                "amount_cny": amount,
                "unit_price_cny": unit_price,
                "reason": reason,
            }
    return result
