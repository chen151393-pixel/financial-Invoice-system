"""合同自动归档作业：只访问 task 表，不执行下载或提交事务。"""

from sqlalchemy import insert, select, update

from ..entity import contract_jobs


def enqueue(connection, task_id, order_ids, actor, now):
    if order_ids:
        connection.execute(
            insert(contract_jobs),
            [
                dict(
                    task_id=task_id,
                    purchase_order_id=order_id,
                    actor=actor,
                    status="pending",
                    created_at=now,
                    updated_at=now,
                )
                for order_id in sorted(set(order_ids))
            ],
        )


def pending(connection, limit=20):
    query = (
        select(contract_jobs)
        .where(contract_jobs.c.status == "pending")
        .order_by(contract_jobs.c.id)
        .limit(limit)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def by_task(connection, task_id):
    query = select(contract_jobs).where(contract_jobs.c.task_id == task_id)
    return {row["purchase_order_id"]: dict(row) for row in connection.execute(query).mappings()}


def complete(connection, task_id, order_id, now):
    connection.execute(
        update(contract_jobs)
        .where(
            contract_jobs.c.task_id == task_id,
            contract_jobs.c.purchase_order_id == order_id,
        )
        .values(status="completed", error_message=None, updated_at=now)
    )


def fail(connection, job_id, message, now):
    # 人工重试已完成时，后台迟到的错误不能将成功状态覆盖为失败。
    connection.execute(
        update(contract_jobs)
        .where(
            contract_jobs.c.id == job_id,
            contract_jobs.c.status == "pending",
        )
        .values(status="failed", error_message=message[:500], updated_at=now)
    )
