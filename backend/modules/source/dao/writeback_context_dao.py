"""回写候选查询所需的来源身份，只访问 source 表。"""

from sqlalchemy import select

from ..entity import companies, parent_orders, purchase_order_lines, purchase_orders, suppliers


def by_lines(connection, line_ids):
    line, order, parent, vendor, company = (
        purchase_order_lines.c,
        purchase_orders.c,
        parent_orders.c,
        suppliers.c,
        companies.c,
    )
    query = (
        select(
            line.id.label("line_id"),
            order.ns_account,
            order.ns_internal_id.label("subpo_id"),
            order.order_no,
            order.parent_relation_status,
            parent.ns_internal_id.label("parent_id"),
            parent.order_no.label("parent_number"),
            parent.ns_account.label("parent_account"),
            parent.supplier_id.label("parent_supplier_id"),
            order.supplier_id,
            vendor.ns_internal_id.label("vendor_id"),
            vendor.name.label("vendor_name"),
            vendor.name_normalized.label("vendor_name_normalized"),
            vendor.ns_account.label("vendor_account"),
            company.ns_internal_id.label("company_ns_id"),
            company.name.label("company_name"),
            company.name_normalized.label("company_name_normalized"),
            company.ns_account.label("company_account"),
            order.company_id,
            parent.currency_internal_id.label("currency_id"),
            line.is_active.label("line_active"),
            order.is_active.label("order_active"),
            parent.is_active.label("parent_active"),
            vendor.is_active.label("vendor_active"),
            company.is_active.label("company_active"),
        )
        .select_from(
            purchase_order_lines.join(purchase_orders, line.purchase_order_id == order.id)
            .outerjoin(parent_orders, order.parent_order_id == parent.id)
            .outerjoin(suppliers, order.supplier_id == vendor.id)
            .outerjoin(companies, order.company_id == company.id)
        )
        .where(line.id.in_(line_ids))
        .order_by(line.id)
    )
    return {r["line_id"]: dict(r) for r in connection.execute(query).mappings()} if line_ids else {}
