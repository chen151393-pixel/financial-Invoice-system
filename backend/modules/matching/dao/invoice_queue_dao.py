"""按整张发票读取待审核队列，不在建议分页后去重。"""

from sqlalchemy import func, select

from ..entity import allocations
from .allocation_dao import _scope


def grouped(connection, *, line_ids=None, invoice_ids=None):
    # 条件先召回发票，再纳入该票的全部待审核建议，避免隐藏同票其他异常。
    matched = select(allocations.c.invoice_id).where(
        allocations.c.status == "proposed", *_scope(line_ids, invoice_ids)
    )
    query = (
        select(
            allocations.c.invoice_id,
            func.min(func.coalesce(allocations.c.confidence, 0)).label("confidence"),
        )
        .where(allocations.c.status == "proposed", allocations.c.invoice_id.in_(matched))
        .group_by(allocations.c.invoice_id)
        .order_by(func.min(func.coalesce(allocations.c.confidence, 0)).desc(), allocations.c.invoice_id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]
