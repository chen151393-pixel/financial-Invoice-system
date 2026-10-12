"""审核冻结的子采购行。"""

from sqlalchemy import insert, select

from ..entity import lines


def insert_lines(connection, review_id, rows, now):
    """按给定顺序写入并返回新行 ID。"""
    ids = []
    for row in rows:
        ids.append(
            connection.execute(
                insert(lines).values(review_id=review_id, created_at=now, updated_at=now, **row)
            ).inserted_primary_key[0]
        )
    return ids


def by_review(connection, review_id):
    query = select(lines).where(lines.c.review_id == review_id).order_by(lines.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]
