"""独立关系结果表查询及保存；沿用调用方事务，不自行提交。"""

from sqlalchemy import and_, null, select

from .relation_entity import RELATION_TABLE


def join_condition(customs, result):
    return and_(
        result.c.tenant_id == customs.c.tenant_id,
        result.c.ns_account == customs.c.ns_account,
        result.c.customs_declaration_id == customs.c.id,
    )


def read_results(connection, tables, tenant, ids, *, include_evidence=True):
    table, customs = tables[RELATION_TABLE], tables["customs_declarations"]
    if not ids:
        return []
    return list(
        connection.execute(
            select(*[column for column in table.c if include_evidence or column.name != "evidence_data"])
            .join(customs, join_condition(customs, table))
            .where(
                customs.c.tenant_id == tenant,
                customs.c.is_active == 1,
                customs.c.id.in_(ids),
            )
        ).mappings()
    )


def save_result(connection, table, values):
    values = dict(values)
    if values["comparison_payload"] is None:
        values["comparison_payload"] = null()
    scope = and_(
        table.c.tenant_id == values["tenant_id"],
        table.c.ns_account == values["ns_account"],
        table.c.customs_declaration_id == values["customs_declaration_id"],
    )
    existing = connection.execute(select(table.c.id).where(scope).with_for_update()).scalar_one_or_none()
    if existing is None:
        connection.execute(table.insert().values(**values))
    else:
        connection.execute(
            table.update().where(scope).values(**{k: v for k, v in values.items() if k != "created_at"})
        )
    return 1
