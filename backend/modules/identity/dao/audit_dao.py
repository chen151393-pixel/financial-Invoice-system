"""身份审计，只追加。"""

from sqlalchemy import insert

from ..entity import audit


def add(connection, actor, action, target, detail, now):
    connection.execute(
        insert(audit).values(actor=actor, action=action, target=target, detail=detail, created_at=now)
    )
