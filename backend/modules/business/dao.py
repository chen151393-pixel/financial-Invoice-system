"""业务库SQL与MySQL命名锁；事务提交由Service控制。"""

from sqlalchemy import and_, func, literal, select, text, union_all

from backend.core.errors import ApiError


def acquire_sync_lock(connection, name):
    return connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": name}).scalar() == 1


def owns_sync_lock(connection, name):
    return (
        connection.execute(text("SELECT IS_USED_LOCK(:name) = CONNECTION_ID()"), {"name": name}).scalar() == 1
    )


def release_sync_lock(connection, name):
    connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})


def save_document(connection, table, line_table, parent_key, document):
    head = document["head"]
    identity = and_(
        table.c.tenant_id == head["tenant_id"],
        table.c.ns_account == head["ns_account"],
        table.c.ns_internal_id == head["ns_internal_id"],
    )
    existing = (
        connection.execute(
            select(table.c.id, table.c.source_data, table.c.source_modified_at)
            .where(identity)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if existing:
        previous = existing["source_data"] or {}
        if previous.get("recordType") not in (None, head["source_data"]["recordType"]) or previous.get(
            "lineType"
        ) not in (None, head["source_data"]["lineType"]):
            raise ApiError(409, "来源记录类型发生变化，不能直接覆盖已保存单据")
        if (
            existing["source_modified_at"]
            and head["source_modified_at"]
            and existing["source_modified_at"] > head["source_modified_at"]
        ):
            raise ApiError(409, "来源版本早于已保存版本，未覆盖本地数据")
        local_id = existing["id"]
        connection.execute(table.update().where(identity).values(**head))
    else:
        local_id = connection.execute(table.insert().values(**head)).inserted_primary_key[0]
    scope = and_(line_table.c.tenant_id == head["tenant_id"], line_table.c[parent_key] == local_id)
    old = dict(connection.execute(select(line_table.c.source_line_key, line_table.c.id).where(scope)).all())
    # 输入已经完整读取和校验；同一短事务内替换有效行集合，失败整体回滚。
    connection.execute(line_table.update().where(scope).values(is_active=False))
    inserted = 0
    for line in document["lines"]:
        values = {**line, parent_key: local_id}
        if line["source_line_key"] in old:
            connection.execute(
                line_table.update()
                .where(scope, line_table.c.id == old[line["source_line_key"]])
                .values(**values)
            )
        else:
            connection.execute(line_table.insert().values(**values))
            inserted += 1
    return local_id, {
        "created": 0 if existing else 1,
        "updated": 1 if existing else 0,
        "linesCreated": inserted,
        "linesUpdated": len(document["lines"]) - inserted,
    }


def local_rows(connection, tables, tenant, account, pl, page):
    branches = []
    for kind, head_name, line_name, parent, pl_column, company_column in (
        ("采购", "purchase_orders", "purchase_order_lines", "purchase_order_id", "head", "head"),
        (
            "报关",
            "customs_declarations",
            "customs_declaration_lines",
            "customs_declaration_id",
            "line",
            "line",
        ),
    ):
        h, line = tables[head_name], tables[line_name]
        p = h if pl_column == "head" else line
        company = h if company_column == "head" else line
        fields = {
            "declaration": h.c.declaration_no if kind == "报关" else literal(None),
            "date": h.c.declaration_date if kind == "报关" else literal(None),
            "sales": line.c.sales_order_no if kind == "报关" else literal(None),
            "parent": h.c.parent_order_no if kind == "采购" else literal(None),
            "purchase": h.c.order_no if kind == "采购" else literal(None),
            "origin": line.c.origin_place if kind == "报关" else literal(None),
            "vendor": h.c.supplier_name if kind == "采购" else literal(None),
            "company": company.c.company_name,
            "name": line.c.declaration_name,
            "spec": line.c.specification,
            "quantity": line.c.quantity,
            "unit": line.c.unit_name,
            "price": line.c.tax_inclusive_price if kind == "采购" else line.c.unit_price,
            "amount": line.c.amount,
            "currency": h.c.currency_code if kind == "采购" else line.c.currency_code,
        }
        branches.append(
            select(
                literal(kind).label("source"),
                literal(0 if kind == "报关" else 1).label("sort_kind"),
                line.c.id,
                company.c.company_identifier,
                h.c.synced_at,
                *[value.label(key) for key, value in fields.items()],
            )
            .select_from(h.join(line, and_(line.c[parent] == h.c.id, line.c.tenant_id == h.c.tenant_id)))
            .where(
                h.c.tenant_id == tenant,
                h.c.ns_account == account,
                h.c.is_active == 1,
                line.c.is_active == 1,
                h.c.last_complete_sync_at.is_not(None),
                p.c.pl_no == pl,
            )
        )
    combined = union_all(*branches).subquery()
    total = connection.execute(select(func.count()).select_from(combined)).scalar_one()
    rows = (
        connection.execute(
            select(combined)
            .order_by(combined.c.company_identifier, combined.c.sort_kind, combined.c.id)
            .limit(50)
            .offset((page - 1) * 50)
        )
        .mappings()
        .all()
    )
    return total, rows
