"""提单读写；不提交事务。"""

from sqlalchemy import insert, select, update

from ..entity.bill import settlement_bills as bills


def active(connection, batch_id):
    """批次未移除的提单，按上传顺序。"""
    query = (
        select(bills).where(bills.c.batch_id == batch_id, bills.c.removed_at.is_(None)).order_by(bills.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def get(connection, batch_id, bill_id):
    query = select(bills).where(bills.c.id == bill_id, bills.c.batch_id == batch_id)
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def insert_bill(connection, values, now):
    result = connection.execute(insert(bills).values(**values, created_at=now, updated_at=now))
    return result.inserted_primary_key[0]


def update_bill(connection, bill_id, values, now):
    connection.execute(update(bills).where(bills.c.id == bill_id).values(**values, updated_at=now))
