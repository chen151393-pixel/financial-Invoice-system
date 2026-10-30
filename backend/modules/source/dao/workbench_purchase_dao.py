"""工作台应开来源：有效报关关联的整张子采购单，不依赖审核或开票任务。"""

from sqlalchemy import select

from ..entity import customs_declarations, customs_purchase_links, purchase_orders


def read(connection):
    query = (
        select(
            purchase_orders.c.id.label("purchase_order_id"),
            purchase_orders.c.ns_account,
            purchase_orders.c.currency,
            purchase_orders.c.total_amount.label("expected"),
            customs_declarations.c.ns_created_at.label("declaration_created_at"),
        )
        .select_from(customs_purchase_links)
        .join(
            customs_declarations, customs_declarations.c.id == customs_purchase_links.c.customs_declaration_id
        )
        .join(purchase_orders, purchase_orders.c.id == customs_purchase_links.c.purchase_order_id)
        .where(
            customs_purchase_links.c.status == "active",
            customs_declarations.c.is_active.is_(True),
            purchase_orders.c.is_active.is_(True),
            purchase_orders.c.ns_account == customs_declarations.c.ns_account,
        )
        .distinct()
    )
    return [dict(row) for row in connection.execute(query).mappings()]
