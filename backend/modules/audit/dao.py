"""审计SQL复用调用方连接，不单独提交事务。"""

from sqlalchemy import insert

from .entity import audit


def append(connection, *, at, actor, action, preview_id):
    connection.execute(insert(audit).values(at=at, actor=actor, action=action, preview_id=preview_id))
