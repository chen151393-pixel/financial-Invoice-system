"""审计SQL复用调用方连接，不单独提交事务。"""

from sqlalchemy import insert

from .entity import finance_audit


def append_finance(connection, *, at, actor, snapshot_id, note):
    connection.execute(insert(finance_audit).values(at=at, actor=actor, snapshot_id=snapshot_id, note=note))
