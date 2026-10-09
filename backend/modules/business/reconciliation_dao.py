"""财务列表读取已同步单据；只沿用 NS 单头外键，不推断汇总行的分摊关系。"""

from sqlalchemy import and_, case, false, func, or_, select

from .relation_dao import read_results


def read_declarations(
    connection,
    tables,
    tenant,
    *,
    keyword,
    account,
    page,
    page_size,
    include_rows,
    status="all",
    approved=(),
    declaration_id=None,
):
    customs = tables["customs_declarations"]
    detail = tables["customs_declaration_lines"]
    purchase = tables["purchase_orders"]
    line = tables["purchase_order_lines"]
    owned = and_(customs.c.tenant_id == tenant, customs.c.is_active == 1)
    linked_purchase = and_(
        purchase.c.customs_declaration_id == customs.c.id,
        purchase.c.tenant_id == customs.c.tenant_id,
        purchase.c.ns_account == customs.c.ns_account,
        purchase.c.is_active == 1,
    )
    linked_detail = and_(
        detail.c.customs_declaration_id == customs.c.id,
        detail.c.tenant_id == customs.c.tenant_id,
        detail.c.is_active == 1,
    )
    linked_line = and_(
        line.c.purchase_order_id == purchase.c.id,
        line.c.tenant_id == purchase.c.tenant_id,
        line.c.is_active == 1,
    )
    accounts = list(
        connection.execute(
            select(customs.c.ns_account).where(owned).distinct().order_by(customs.c.ns_account)
        ).scalars()
    )
    criteria = [owned]
    if account:
        criteria.append(customs.c.ns_account == account)
    if declaration_id is not None:
        criteria.append(customs.c.ns_internal_id == declaration_id)
    if keyword:

        def contains(*columns):
            return or_(*(column.icontains(keyword, autoescape=True) for column in columns))

        criteria.append(
            or_(
                contains(customs.c.record_no, customs.c.declaration_no, customs.c.declarant_name),
                select(detail.c.id)
                .where(
                    linked_detail,
                    contains(
                        detail.c.pl_no,
                        detail.c.declaration_name,
                        detail.c.specification,
                        detail.c.company_name,
                    ),
                )
                .exists(),
                select(purchase.c.id)
                .where(
                    linked_purchase,
                    contains(
                        purchase.c.order_no,
                        purchase.c.parent_order_no,
                        purchase.c.pl_no,
                        purchase.c.supplier_name,
                    ),
                )
                .exists(),
                select(line.c.id)
                .select_from(purchase.join(line, linked_line))
                .where(
                    linked_purchase, contains(line.c.item_name, line.c.declaration_name, line.c.specification)
                )
                .exists(),
            )
        )
    reviewed = or_(
        false(),
        *(
            and_(
                customs.c.ns_account == row["account"],
                customs.c.ns_internal_id == row["declaration_id"],
            )
            for row in approved
        ),
    )
    state = case((reviewed, "approved"), else_="pending")
    counts = {"pending": 0, "approved": 0, "blocked": 0}
    counts.update(
        dict(
            connection.execute(
                select(state.label("state"), func.count())
                .select_from(customs)
                .where(*criteria)
                .group_by(state)
            ).all()
        )
    )
    counts["all"] = sum(counts.values())
    total = counts[status]
    if status != "all":
        criteria.append(state == status)
    if not include_rows:
        return {
            "total": total,
            "counts": counts,
            "accounts": accounts,
            "heads": [],
            "details": [],
            "purchases": [],
            "lines": [],
        }
    # 先对轻量主键分页，避免含原始关系大JSON的整行参与MySQL排序而耗尽sort buffer。
    ids = list(
        connection.execute(
            select(customs.c.id)
            .select_from(customs)
            .where(*criteria)
            .order_by(customs.c.declaration_date.desc(), customs.c.record_no.desc(), customs.c.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).scalars()
    )
    heads_by_id = (
        {
            row["id"]: row
            for row in connection.execute(select(customs).where(owned, customs.c.id.in_(ids))).mappings()
        }
        if ids
        else {}
    )
    heads = [heads_by_id[identity] for identity in ids]
    details = (
        connection.execute(
            select(detail)
            .join(customs, linked_detail)
            .where(owned, customs.c.id.in_(ids))
            .order_by(detail.c.line_no, detail.c.id)
        )
        .mappings()
        .all()
        if ids
        else []
    )
    purchases = (
        connection.execute(
            select(purchase)
            .join(customs, linked_purchase)
            .where(owned, customs.c.id.in_(ids))
            .order_by(purchase.c.order_no, purchase.c.id)
        )
        .mappings()
        .all()
        if ids
        else []
    )
    lines = (
        connection.execute(
            select(line)
            .join(purchase, linked_line)
            .join(customs, linked_purchase)
            .where(owned, customs.c.id.in_(ids))
            .order_by(purchase.c.order_no, line.c.line_no, line.c.id)
        )
        .mappings()
        .all()
        if ids
        else []
    )
    return {
        "total": total,
        "counts": counts,
        "accounts": accounts,
        "relation_results": read_results(connection, tables, tenant, ids),
        "heads": heads,
        "details": details,
        "purchases": purchases,
        "lines": lines,
    }
