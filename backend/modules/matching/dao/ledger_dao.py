"""分配台账读取，历史取消仍参与摘要；待复核确认仍占用发票额度。"""

from sqlalchemy import select

from ..entity import allocations


def by_lines(connection, line_ids, *, lock=False):
    query = select(allocations).where(allocations.c.purchase_line_id.in_(line_ids)).order_by(allocations.c.id)
    if lock:
        query = query.with_for_update()
    return [dict(r) for r in connection.execute(query).mappings()] if line_ids else []


def unresolved(connection, invoice_id, line_id, exclude_id=None):
    query = select(allocations.c.id).where(
        (allocations.c.invoice_id == invoice_id) | (allocations.c.purchase_line_id == line_id),
        allocations.c.status == "confirmed",
        allocations.c.verification_status != "valid",
    )
    if exclude_id is not None:
        query = query.where(allocations.c.id != exclude_id)
    return connection.execute(query.limit(1)).first() is not None
