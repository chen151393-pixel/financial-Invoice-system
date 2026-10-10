"""NS 原始数据：内容相同不重复保存，内容变化追加一行。"""

import hashlib
import json

from sqlalchemy import insert, select

from ..entity import raw_records


def digest(payload):
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def save(connection, account, record_type, ns_internal_id, payload, now):
    sha = digest(payload)
    identity = (
        raw_records.c.ns_account == account,
        raw_records.c.record_type == record_type,
        raw_records.c.ns_internal_id == ns_internal_id,
        raw_records.c.payload_sha256 == sha,
    )
    existing = connection.execute(select(raw_records.c.id).where(*identity)).scalar()
    if existing is not None:
        return existing
    return connection.execute(
        insert(raw_records).values(
            ns_account=account,
            record_type=record_type,
            ns_internal_id=ns_internal_id,
            payload=payload,
            payload_sha256=sha,
            fetched_at=now,
            created_at=now,
            updated_at=now,
        )
    ).inserted_primary_key[0]


def payloads(connection, ids):
    if not ids:
        return {}
    rows = connection.execute(
        select(raw_records.c.id, raw_records.c.payload).where(raw_records.c.id.in_(ids))
    )
    return {row.id: row.payload for row in rows}


def latest(connection, account, record_type, ns_internal_id):
    """该来源最近一次保存的原始数据；没有时返回 None。"""
    return connection.execute(
        select(raw_records.c.payload)
        .where(
            raw_records.c.ns_account == account,
            raw_records.c.record_type == record_type,
            raw_records.c.ns_internal_id == ns_internal_id,
        )
        .order_by(raw_records.c.id.desc())
        .limit(1)
    ).scalar()
