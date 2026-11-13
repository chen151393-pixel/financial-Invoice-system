"""海关审核版本查询与保存；事务由用例管理。"""

from sqlalchemy import insert, select

from ..entity.customs_approval import customs_approvals


def current(connection, head, declaration_id, source_sha256):
    query = select(customs_approvals).where(
        customs_approvals.c.receipt_id == head["id"],
        customs_approvals.c.receipt_revision == head["revision"],
        customs_approvals.c.receipt_sha256 == head["content_sha256"],
        customs_approvals.c.customs_declaration_id == declaration_id,
        customs_approvals.c.source_sha256 == source_sha256,
    )
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def approve(connection, values, now):
    return connection.execute(
        insert(customs_approvals).values(**values, approved_at=now, created_at=now, updated_at=now)
    ).inserted_primary_key[0]
