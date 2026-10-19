"""工作台比对待办：未审核建议及已确认但需复核的分配。"""

from sqlalchemy import and_, or_, select

from ..entity import allocations


def read(connection):
    query = select(allocations).where(
        or_(
            allocations.c.status == "proposed",
            and_(allocations.c.status == "confirmed", allocations.c.verification_status != "valid"),
        )
    )
    return [dict(row) for row in connection.execute(query).mappings()]
