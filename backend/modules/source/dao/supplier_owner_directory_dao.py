"""人员关联使用的 source 主数据及已出现的供应商、采购公司组合，只读。"""

from sqlalchemy import select

from ..entity import companies, purchase_orders, suppliers


def directory(connection):
    return {
        "suppliers": [
            dict(row)
            for row in connection.execute(
                select(suppliers).order_by(suppliers.c.name, suppliers.c.id)
            ).mappings()
        ],
        "companies": [
            dict(row)
            for row in connection.execute(
                select(companies)
                .where(companies.c.id.in_(select(purchase_orders.c.company_id)))
                .order_by(companies.c.name, companies.c.id)
            ).mappings()
        ],
        "pairs": [
            dict(row)
            for row in connection.execute(
                select(purchase_orders.c.supplier_id, purchase_orders.c.company_id)
                .where(
                    purchase_orders.c.is_active.is_(True),
                    purchase_orders.c.supplier_id.is_not(None),
                    purchase_orders.c.company_id.is_not(None),
                )
                .distinct()
            ).mappings()
        ],
    }
