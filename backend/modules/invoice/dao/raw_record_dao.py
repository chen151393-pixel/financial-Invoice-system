"""柠檬云原始数据：同来源、同账套、同记录、同内容只保存一次。"""

from sqlalchemy import insert, select

from ..entity import raw_records


def save(connection, values, now):
    """values：source、lemon_account、external_id、payload、payload_sha256；返回 ID。"""
    existing = connection.execute(
        select(raw_records.c.id).where(
            raw_records.c.source == values["source"],
            raw_records.c.lemon_account == values["lemon_account"],
            raw_records.c.external_id == values["external_id"],
            raw_records.c.payload_sha256 == values["payload_sha256"],
        )
    ).scalar()
    if existing:
        return existing
    return connection.execute(
        insert(raw_records).values(fetched_at=now, created_at=now, updated_at=now, **values)
    ).inserted_primary_key[0]
