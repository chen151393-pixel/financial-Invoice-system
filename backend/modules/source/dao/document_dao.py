"""单头 + 明细的保存规则（子采购单、报关单共用），在调用方事务中执行。

- 按 NS 账套 + NS 内部 ID 识别同一单据；
- 来源修改时间早于已保存版本时拒绝覆盖；记录类型变化时拒绝覆盖；
- 明细按稳定行键更新，本次未返回的明细置为无效，不删除。
"""

from sqlalchemy import insert, select, update

from backend.core.errors import ApiError

from ..entity import raw_records


def save(connection, table, line_table, parent_key, account, ns_internal_id, head, lines, now):
    existing = (
        connection.execute(
            select(table.c.id, table.c.source_modified_at, raw_records.c.record_type)
            .select_from(table.outerjoin(raw_records, raw_records.c.id == table.c.raw_record_id))
            .where(table.c.ns_account == account, table.c.ns_internal_id == ns_internal_id)
            .with_for_update(of=table)
        )
        .mappings()
        .first()
    )
    if existing:
        new_type = connection.execute(
            select(raw_records.c.record_type).where(raw_records.c.id == head["raw_record_id"])
        ).scalar()
        if existing["record_type"] not in (None, new_type):
            raise ApiError(409, "来源记录类型发生变化，不能直接覆盖已保存单据")
        previous, current = existing["source_modified_at"], head.get("source_modified_at")
        if previous and current and previous > current:
            raise ApiError(409, "来源版本早于已保存版本，未覆盖本地数据")
        local_id = existing["id"]
        connection.execute(update(table).where(table.c.id == local_id).values(updated_at=now, **head))
    else:
        local_id = connection.execute(
            insert(table).values(
                ns_account=account, ns_internal_id=ns_internal_id, created_at=now, updated_at=now, **head
            )
        ).inserted_primary_key[0]
    scope = line_table.c[parent_key] == local_id
    old = dict(connection.execute(select(line_table.c.source_line_key, line_table.c.id).where(scope)).all())
    # 输入已完整读取和校验；同一事务内替换有效行集合，失败整体回滚。
    connection.execute(update(line_table).where(scope).values(is_active=False, updated_at=now))
    inserted = 0
    for line in lines:
        values = {**line, parent_key: local_id, "is_active": True, "updated_at": now}
        if line["source_line_key"] in old:
            connection.execute(
                update(line_table).where(line_table.c.id == old[line["source_line_key"]]).values(**values)
            )
        else:
            connection.execute(insert(line_table).values(created_at=now, **values))
            inserted += 1
    line_ids = dict(
        connection.execute(
            select(line_table.c.source_line_key, line_table.c.id).where(
                scope, line_table.c.is_active.is_(True)
            )
        ).all()
    )
    counts = {
        "created": 0 if existing else 1,
        "updated": 1 if existing else 0,
        "linesCreated": inserted,
        "linesUpdated": len(lines) - inserted,
    }
    return local_id, counts, line_ids
