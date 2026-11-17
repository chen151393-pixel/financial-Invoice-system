"""合同抬头读写；不提交事务。"""

from sqlalchemy import insert, select, update

from ..entity.party import settlement_parties as parties


def all_parties(connection):
    return [dict(row) for row in connection.execute(select(parties).order_by(parties.c.name)).mappings()]


def get(connection, party_id):
    row = connection.execute(select(parties).where(parties.c.id == party_id)).mappings().first()
    return dict(row) if row else None


def by_ids(connection, party_ids):
    if not party_ids:
        return {}
    query = select(parties).where(parties.c.id.in_(party_ids))
    return {row["id"]: dict(row) for row in connection.execute(query).mappings()}


def by_key(connection, name_key):
    row = connection.execute(select(parties).where(parties.c.name_key == name_key)).mappings().first()
    return dict(row) if row else None


def insert_party(connection, values, now):
    result = connection.execute(insert(parties).values(**values, created_at=now, updated_at=now))
    return result.inserted_primary_key[0]


def update_party(connection, party_id, values, now):
    connection.execute(update(parties).where(parties.c.id == party_id).values(**values, updated_at=now))
