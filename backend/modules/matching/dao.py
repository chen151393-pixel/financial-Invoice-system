"""分配查询与写入；事务和规则由服务管理。"""

from sqlalchemy import select

from .entity import allocations, link_batches, link_pairs


def read(connection, tenant, lock=False):
    query = select(allocations).where(allocations.c.tenant_id == tenant).order_by(allocations.c.id)
    if lock:
        query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def insert(connection, values):
    connection.execute(allocations.insert().values(**values))


def read_links(connection, tenant, lock=False):
    query = (
        select(link_batches, link_pairs)
        .join(link_pairs, link_pairs.c.batch_id == link_batches.c.id)
        .where(link_batches.c.tenant_id == tenant, link_pairs.c.tenant_id == tenant)
        .order_by(link_batches.c.id, link_pairs.c.id)
    )
    if lock:
        query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def insert_links(connection, batch, pairs):
    batch_id = connection.execute(link_batches.insert().values(**batch)).inserted_primary_key[0]
    connection.execute(link_pairs.insert(), [{**pair, "batch_id": batch_id} for pair in pairs])
