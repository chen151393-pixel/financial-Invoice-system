"""结汇批次头表读写；不提交事务、不决定状态。"""

from sqlalchemy import func, insert, select, update

from ..entity.batch import settlement_batches as batches


def get(connection, batch_id, *, lock=False):
    query = select(batches).where(batches.c.id == batch_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def by_request(connection, request_id):
    row = connection.execute(select(batches).where(batches.c.request_id == request_id)).mappings().first()
    return dict(row) if row else None


def insert_batch(connection, values, now):
    result = connection.execute(insert(batches).values(**values, created_at=now, updated_at=now))
    return result.inserted_primary_key[0]


def update_batch(connection, batch_id, values, now):
    connection.execute(update(batches).where(batches.c.id == batch_id).values(**values, updated_at=now))


def _conditions(filters):
    conditions = []
    if filters.get("route"):
        conditions.append(batches.c.route == filters["route"])
    if filters.get("statuses"):
        conditions.append(batches.c.status.in_(filters["statuses"]))
    if filters.get("consignee"):
        conditions.append(batches.c.consignee.contains(filters["consignee"], autoescape=True))
    if filters.get("batch_no"):
        conditions.append(batches.c.batch_no.contains(filters["batch_no"], autoescape=True))
    if filters.get("received_from"):
        conditions.append(batches.c.received_on >= filters["received_from"])
    if filters.get("received_to"):
        conditions.append(batches.c.received_on <= filters["received_to"])
    if filters.get("ids") is not None:
        conditions.append(batches.c.id.in_(filters["ids"]))
    return conditions


def page(connection, filters, offset, limit):
    conditions = _conditions(filters)
    total = connection.execute(select(func.count()).select_from(batches).where(*conditions)).scalar_one()
    query = (
        select(batches)
        .where(*conditions)
        .order_by(batches.c.received_on.desc(), batches.c.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return total, [dict(row) for row in connection.execute(query).mappings()]


def status_counts(connection, filters):
    """按（路径, 状态）计数，忽略状态筛选：{(route, status): 张数}。"""
    conditions = _conditions({**filters, "statuses": None})
    query = (
        select(batches.c.route, batches.c.status, func.count())
        .where(*conditions)
        .group_by(batches.c.route, batches.c.status)
    )
    return {(route, status): count for route, status, count in connection.execute(query)}
