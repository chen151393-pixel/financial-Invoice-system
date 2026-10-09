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


def relation_backfill_sources(connection, tables, tenant, account, ids):
    customs, purchases = tables["customs_declarations"], tables["purchase_orders"]
    heads = (
        connection.execute(
            select(
                customs.c.id,
                customs.c.tenant_id,
                customs.c.ns_account,
                customs.c.ns_internal_id,
                customs.c.record_no,
                customs.c.source_data,
                customs.c.synced_at,
            ).where(
                customs.c.tenant_id == tenant,
                customs.c.ns_account == account,
                customs.c.is_active == 1,
                customs.c.ns_internal_id.in_(ids),
            )
        )
        .mappings()
        .all()
    )
    children = (
        connection.execute(
            select(
                purchases.c.id, purchases.c.ns_internal_id, purchases.c.source_data, purchases.c.synced_at
            ).where(
                purchases.c.tenant_id == tenant,
                purchases.c.ns_account == account,
                purchases.c.is_active == 1,
                purchases.c.customs_declaration_id.in_([row["id"] for row in heads]),
            )
        )
        .mappings()
        .all()
    )
    # 已按单据范围限定，取回后按主键对齐快照；不让大JSON参与MySQL排序。
    return {
        "customs": sorted([dict(row) for row in heads], key=lambda row: row["id"]),
        "purchases": sorted([dict(row) for row in children], key=lambda row: row["id"]),
    }


def relation_backfill_ids(connection, table, tenant, account):
    return list(
        connection.execute(
            select(table.c.ns_internal_id)
            .where(table.c.tenant_id == tenant, table.c.ns_account == account, table.c.is_active == 1)
            .order_by(table.c.id)
        ).scalars()
    )


def lock_relation_backfill_sources(connection, tables, tenant, account, ids):
    for name in ("customs_declarations", "purchase_orders"):
        table = tables[name]
        connection.execute(
            select(table.c.id)
            .where(table.c.tenant_id == tenant, table.c.ns_account == account, table.c.is_active == 1)
            .order_by(table.c.id)
            .with_for_update()
        ).all()
    return relation_backfill_sources(connection, tables, tenant, account, ids)


def previous_customs_dependencies(connection, tables, tenant, account, purchase_ids, refreshed_ids):
    """读取本次子采购原来关联、但不在本次完整刷新范围内的报关单。"""
    customs, purchase = tables["customs_declarations"], tables["purchase_orders"]
    return list(
        connection.execute(
            select(
                customs.c.id,
                customs.c.tenant_id,
                customs.c.ns_account,
                customs.c.ns_internal_id,
                customs.c.record_no,
            )
            .where(
                customs.c.tenant_id == tenant,
                customs.c.ns_account == account,
                customs.c.is_active == 1,
                customs.c.ns_internal_id.not_in(refreshed_ids),
                select(purchase.c.id)
                .where(
                    purchase.c.tenant_id == tenant,
                    purchase.c.ns_account == account,
                    purchase.c.ns_internal_id.in_(purchase_ids),
                    purchase.c.customs_declaration_id == customs.c.id,
                )
                .exists(),
            )
            .with_for_update()
        ).mappings()
    )


def save_document(connection, table, line_table, parent_key, document):
    head = document["head"]
    identity = and_(
        table.c.tenant_id == head["tenant_id"],
        table.c.ns_account == head["ns_account"],
        table.c.ns_internal_id == head["ns_internal_id"],
    )
    if "ns_record_type" in table.c:
        identity = and_(identity, table.c.ns_record_type == head["ns_record_type"])
    existing_columns = [table.c.id, table.c.source_data, table.c.source_modified_at]
    has_parent_relation = "parent_purchase_order_id" in head and table.name == "purchase_orders"
    if has_parent_relation:
        existing_columns.append(table.c.parent_purchase_order_id)
    existing = (
        connection.execute(select(*existing_columns).where(identity).with_for_update()).mappings().first()
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
        if has_parent_relation and existing["parent_purchase_order_id"] != head["parent_purchase_order_id"]:
            # 母单引用变化时，先解除旧子行的组合外键，再在同一事务内建立新关联。
            connection.execute(
                line_table.update()
                .where(line_table.c.tenant_id == head["tenant_id"], line_table.c[parent_key] == local_id)
                .values(parent_purchase_order_id=None, parent_purchase_order_line_id=None)
            )
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


def document_line_ids(connection, table, tenant, parent_key, parent_id):
    return dict(
        connection.execute(
            select(table.c.source_line_key, table.c.id).where(
                table.c.tenant_id == tenant, table.c[parent_key] == parent_id, table.c.is_active == 1
            )
        ).all()
    )


def clear_missing_customs_links(connection, table, tenant, account, customs_id, purchase_ids):
    """本次已完整反查引用；解除来源已移出的旧外键，不删除采购单或其他账套数据。"""
    connection.execute(
        table.update()
        .where(
            table.c.tenant_id == tenant,
            table.c.ns_account == account,
            table.c.customs_declaration_id == customs_id,
            table.c.ns_internal_id.not_in(purchase_ids),
        )
        .values(customs_declaration_id=None)
    )


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


def matching_sources(connection, tables, tenant, lock=False):
    head, line = tables["purchase_orders"], tables["purchase_order_lines"]
    customs = tables["customs_declarations"]
    parent = tables["parent_purchase_orders"]
    if lock:
        # 所有确认按采购主键顺序锁定，与来源更新共享行锁，防止并发超分配。
        connection.execute(
            select(head.c.id)
            .where(head.c.tenant_id == tenant, head.c.is_active == 1)
            .order_by(head.c.id)
            .with_for_update()
        ).all()
    heads = (
        connection.execute(
            select(
                *[
                    head.c[key]
                    for key in (
                        "id",
                        "supplier_name",
                        "order_no",
                        "currency_code",
                        "total_amount",
                        "ns_account",
                        "parent_order_no",
                        "company_name",
                        "detail_sync_status",
                        "customs_declaration_id",
                        "parent_purchase_order_id",
                    )
                ],
                customs.c.record_no.label("customs_record_no"),
                customs.c.declaration_no.label("customs_declaration_no"),
                parent.c.currency_code.label("parent_currency_code"),
                parent.c.order_no.label("verified_parent_order_no"),
            )
            .select_from(
                head.outerjoin(
                    customs,
                    (head.c.customs_declaration_id == customs.c.id)
                    & (head.c.tenant_id == customs.c.tenant_id)
                    & (head.c.ns_account == customs.c.ns_account)
                    & (customs.c.is_active == 1),
                ).outerjoin(
                    parent,
                    (head.c.parent_purchase_order_id == parent.c.id)
                    & (head.c.tenant_id == parent.c.tenant_id)
                    & (head.c.ns_account == parent.c.ns_account)
                    & (parent.c.is_active == 1),
                )
            )
            .where(head.c.tenant_id == tenant, head.c.is_active == 1)
            .order_by(head.c.id)
            .with_for_update(read=not lock)
        )
        .mappings()
        .all()
    )
    lines = (
        connection.execute(
            select(line)
            .join(head, line.c.purchase_order_id == head.c.id)
            .where(
                head.c.tenant_id == tenant,
                head.c.is_active == 1,
                line.c.tenant_id == tenant,
                line.c.is_active == 1,
            )
            .order_by(line.c.id)
            .with_for_update(read=not lock)
        )
        .mappings()
        .all()
    )
    return heads, lines
