"""账单目标锁：唯一约束保证同一账单同时只属于一个写入请求。"""

from sqlalchemy import select

from ..entity import target_locks


def holders(connection, account, bill_ids):
    return {
        row.bill_id: row.request_id
        for row in connection.execute(
            select(target_locks.c.bill_id, target_locks.c.request_id).where(
                target_locks.c.ns_account == account, target_locks.c.bill_id.in_(bill_ids)
            )
        )
    }


def acquire(connection, account, bill_ids, request_id, stamp):
    # 按账单 ID 排序加锁，避免两张发票交叉等待。
    for bill_id in sorted(bill_ids, key=int):
        connection.execute(
            target_locks.insert().values(
                ns_account=account, bill_id=bill_id, request_id=request_id, created_at=stamp, updated_at=stamp
            )
        )


def release(connection, request_id):
    connection.execute(target_locks.delete().where(target_locks.c.request_id == request_id))
