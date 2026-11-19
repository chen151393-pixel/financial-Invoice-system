"""销售合同记录读写；不提交事务。"""

from sqlalchemy import delete, insert, select

from ..entity.contract import settlement_contracts as contracts
from .document_scope import condition
from .document_scope import values as scope_values


def of_batch(connection, batch_id):
    query = select(contracts).where(condition(contracts, batch_id)).order_by(contracts.c.contract_no)
    return [dict(row) for row in connection.execute(query).mappings()]


def get(connection, batch_id, contract_id):
    query = select(contracts).where(contracts.c.id == contract_id, condition(contracts, batch_id))
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def replace(connection, batch_id, rows, now):
    """重新生成：整批替换该批次的合同记录。"""
    connection.execute(delete(contracts).where(condition(contracts, batch_id)))
    if rows:
        connection.execute(
            insert(contracts),
            [{**row, **scope_values(batch_id), "created_at": now, "updated_at": now} for row in rows],
        )


def latest_seller(connection):
    """最近一次生成使用的卖方抬头 ID，作为生成表单的默认值。"""
    query = select(contracts.c.seller_party_id).order_by(contracts.c.id.desc()).limit(1)
    return connection.execute(query).scalar()
