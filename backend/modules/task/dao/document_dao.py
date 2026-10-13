"""子采购合同记录：只保存共享盘路径与校验值。"""

from sqlalchemy import insert, select, update

from ..entity import documents


def by_task(connection, task_id):
    query = select(documents).where(documents.c.task_id == task_id).order_by(documents.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def get(connection, task_id, purchase_order_id, *, lock=False):
    query = select(documents).where(
        documents.c.task_id == task_id, documents.c.purchase_order_id == purchase_order_id
    )
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def insert_document(connection, values, now):
    return connection.execute(
        insert(documents).values(status="pending", created_at=now, updated_at=now, **values)
    ).inserted_primary_key[0]


def update_document(connection, document_id, values, now):
    connection.execute(
        update(documents).where(documents.c.id == document_id).values(updated_at=now, **values)
    )
