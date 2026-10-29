"""写入请求存取；调用方管理事务和状态。"""

from sqlalchemy import select

from ..entity import requests


def add(connection, values, stamp):
    return connection.execute(
        requests.insert().values(**values, created_at=stamp, updated_at=stamp)
    ).inserted_primary_key[0]


def by_plan(connection, plan_id):
    row = (
        connection.execute(select(requests).where(requests.c.plan_id == plan_id).with_for_update())
        .mappings()
        .first()
    )
    return dict(row) if row else None


def change(connection, request_id, values, stamp):
    connection.execute(
        requests.update().where(requests.c.id == request_id).values(**values, updated_at=stamp)
    )
