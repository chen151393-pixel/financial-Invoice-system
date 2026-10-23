"""报关资料记录：只访问 task_declaration_documents，不下载文件、不决定任务状态。"""

from sqlalchemy import insert, select, update

from ..entity import declaration_documents
from ..entity.declaration_document import DOC_TYPES


def ensure(connection, declaration_id, account, record_no, actor, now):
    """为报关单登记三类资料的待下载记录；已有记录（含已归档）保持不变。"""
    existing = set(
        connection.execute(
            select(declaration_documents.c.doc_type).where(
                declaration_documents.c.customs_declaration_id == declaration_id
            )
        ).scalars()
    )
    rows = [
        dict(
            customs_declaration_id=declaration_id,
            ns_account=account,
            record_no=record_no,
            doc_type=doc_type,
            status="pending",
            requested_by=actor,
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        for doc_type in DOC_TYPES
        if doc_type not in existing
    ]
    if rows:
        connection.execute(insert(declaration_documents), rows)


def by_declarations(connection, declaration_ids):
    """{报关单 ID: {资料类型: 记录}}。"""
    if not declaration_ids:
        return {}
    query = select(declaration_documents).where(
        declaration_documents.c.customs_declaration_id.in_(declaration_ids)
    )
    result = {}
    for row in connection.execute(query).mappings():
        result.setdefault(row["customs_declaration_id"], {})[row["doc_type"]] = dict(row)
    return result


def get(connection, declaration_id, doc_type, *, lock=False):
    query = select(declaration_documents).where(
        declaration_documents.c.customs_declaration_id == declaration_id,
        declaration_documents.c.doc_type == doc_type,
    )
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def pending(connection, limit=20):
    query = (
        select(declaration_documents)
        .where(declaration_documents.c.status == "pending")
        .order_by(declaration_documents.c.id)
        .limit(limit)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def start_attempt(connection, document_id, actor, now):
    connection.execute(
        update(declaration_documents)
        .where(declaration_documents.c.id == document_id)
        .values(
            attempts=declaration_documents.c.attempts + 1,
            requested_by=actor,
            updated_at=now,
        )
    )


def archived(connection, document_id, files, ns_id, now):
    connection.execute(
        update(declaration_documents)
        .where(declaration_documents.c.id == document_id)
        .values(
            status="archived",
            files=files,
            ns_id=ns_id,
            error_message=None,
            archived_at=now,
            updated_at=now,
        )
    )


def failed(connection, document_id, message, now):
    # 已归档的资料重新下载失败时保留已归档状态，只有未归档的记为失败。
    connection.execute(
        update(declaration_documents)
        .where(
            declaration_documents.c.id == document_id,
            declaration_documents.c.status != "archived",
        )
        .values(status="failed", error_message=message[:500], updated_at=now)
    )
