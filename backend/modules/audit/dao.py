"""审计SQL复用调用方连接，不单独提交事务。"""

from sqlalchemy import insert

from .entity import audit, finance_audit


def append(connection, *, at, actor, action, preview_id):
    connection.execute(insert(audit).values(at=at, actor=actor, action=action, preview_id=preview_id))


def append_finance(connection, *, at, actor, snapshot_id, note):
    connection.execute(insert(finance_audit).values(at=at, actor=actor, snapshot_id=snapshot_id, note=note))
