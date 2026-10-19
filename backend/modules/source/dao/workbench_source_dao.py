"""工作台报关索引和关联名称；只读取 source 表，不带原始报文。"""

from sqlalchemy import select

from ..entity import (
    companies,
    customs_declarations,
    customs_lines,
    customs_purchase_links,
    purchase_orders,
    suppliers,
)
from .customs_declaration_dao import index


def read(connection):
    states = {row["id"]: row for row in index(connection, "", "")}
    heads = connection.execute(
        select(customs_declarations, companies.c.name.label("company"))
        .outerjoin(companies, companies.c.id == customs_declarations.c.declarant_company_id)
        .where(customs_declarations.c.is_active.is_(True))
    ).mappings()
    result = {
        row["id"]: {**dict(row), **states[row["id"]], "pls": set(), "suppliers": set()} for row in heads
    }
    for row in connection.execute(
        select(customs_lines.c.customs_declaration_id, customs_lines.c.pl_no).where(
            customs_lines.c.is_active.is_(True)
        )
    ):
        if row.customs_declaration_id in result and row.pl_no:
            result[row.customs_declaration_id]["pls"].add(row.pl_no)
    query = (
        select(customs_purchase_links.c.customs_declaration_id, suppliers.c.name)
        .join(purchase_orders, purchase_orders.c.id == customs_purchase_links.c.purchase_order_id)
        .outerjoin(suppliers, suppliers.c.id == purchase_orders.c.supplier_id)
        .where(customs_purchase_links.c.status == "active")
    )
    for row in connection.execute(query):
        if row.customs_declaration_id in result and row.name:
            result[row.customs_declaration_id]["suppliers"].add(row.name)
    return list(result.values())
