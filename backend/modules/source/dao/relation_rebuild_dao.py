"""本地关联补算的分页范围；不读取 NS，也不跨模块访问表。"""

from sqlalchemy import select

from ..entity import customs_declarations


def page(connection, after=0, *, record_no=None, account=None):
    table = customs_declarations
    query = select(table.c.id, table.c.ns_account).where(table.c.is_active.is_(True), table.c.id > after)
    if record_no:
        query = query.where(table.c.record_no == record_no)
    if account:
        query = query.where(table.c.ns_account == account)
    return [dict(row) for row in connection.execute(query.order_by(table.c.id).limit(100)).mappings()]
