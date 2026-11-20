"""银行水单原件读写；复用批次事务，不自行提交。"""

from sqlalchemy import insert, select

from ..entity.batch import settlement_batches as batches
from ..entity.hk_slip import settlement_hk_slips as slips


def get(connection, batch_id):
    row = connection.execute(select(slips).where(slips.c.batch_id == batch_id)).mappings().first()
    return dict(row) if row else None


def save(connection, batch_id, values, owner, now):
    connection.execute(
        insert(slips).values(batch_id=batch_id, **values, uploaded_by=owner, created_at=now, updated_at=now)
    )


def accounts(connection):
    query = (
        select(batches.c.receiving_account)
        .where(
            batches.c.route == "hk_transit",
            batches.c.receiving_account.is_not(None),
            batches.c.receiving_account != "",
        )
        .distinct()
        .order_by(batches.c.receiving_account)
    )
    return [r[0] for r in connection.execute(query)]
