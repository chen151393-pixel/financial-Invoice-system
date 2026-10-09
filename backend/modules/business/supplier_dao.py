"""从当前身份的有效采购来源读取供应商，不按名称合并身份。"""

from sqlalchemy import func, or_, select


def suppliers(connection, tables, tenant, *, keyword="", account="", supplier_id="", page=1, page_size=20):
    purchase = tables["purchase_orders"]
    criteria = [
        purchase.c.tenant_id == tenant,
        purchase.c.is_active == 1,
        purchase.c.supplier_identifier.is_not(None),
        func.trim(purchase.c.supplier_identifier) != "",
    ]
    if account:
        criteria.append(purchase.c.ns_account == account)
    if supplier_id:
        criteria.append(purchase.c.supplier_identifier == supplier_id)
    if keyword:
        criteria.append(
            or_(
                purchase.c.supplier_name.icontains(keyword, autoescape=True),
                purchase.c.supplier_identifier.icontains(keyword, autoescape=True),
            )
        )
    query = (
        select(
            purchase.c.ns_account.label("account"),
            purchase.c.supplier_identifier.label("supplierId"),
            func.coalesce(func.min(purchase.c.supplier_name), purchase.c.supplier_identifier).label(
                "supplierName"
            ),
        )
        .where(*criteria)
        .group_by(purchase.c.ns_account, purchase.c.supplier_identifier)
    )
    total = connection.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = (
        connection.execute(
            query.order_by(purchase.c.ns_account, purchase.c.supplier_identifier)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .mappings()
        .all()
    )
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }
