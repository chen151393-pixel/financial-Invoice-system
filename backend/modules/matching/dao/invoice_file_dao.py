"""发票文件记录：只访问 matching_invoice_files，不写文件、不判断发票能否归档。"""

from sqlalchemy import insert, select

from ..entity import invoice_files


def get(connection, invoice_id, declaration_id, *, lock=False):
    query = select(invoice_files).where(
        invoice_files.c.invoice_id == invoice_id,
        invoice_files.c.customs_declaration_id == declaration_id,
    )
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def insert_file(connection, values, now):
    connection.execute(insert(invoice_files).values(created_at=now, updated_at=now, **values))
