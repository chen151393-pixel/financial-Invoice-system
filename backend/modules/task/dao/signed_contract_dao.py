"""回签合同记录：只访问 task_signed_contracts，不写文件、不决定任务状态。"""

from sqlalchemy import insert, select

from ..entity import signed_contracts


def by_orders(connection, order_ids):
    if not order_ids:
        return {}
    query = select(signed_contracts).where(signed_contracts.c.purchase_order_id.in_(order_ids))
    return {row["purchase_order_id"]: dict(row) for row in connection.execute(query).mappings()}


def get(connection, order_id, *, lock=False):
    query = select(signed_contracts).where(signed_contracts.c.purchase_order_id == order_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def insert_contract(connection, values, now):
    connection.execute(insert(signed_contracts).values(created_at=now, updated_at=now, **values))
