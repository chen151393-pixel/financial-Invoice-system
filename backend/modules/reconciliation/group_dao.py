"""群配置查询与条件写入；事务及权限由调用方管理。"""

from sqlalchemy import func, insert, or_, select, update

from .group_entity import bindings


def binding(connection, owner, account, supplier_id):
    return (
        connection.execute(
            select(bindings).where(
                bindings.c.owner == owner,
                bindings.c.account == account,
                bindings.c.supplier_id == supplier_id,
            )
        )
        .mappings()
        .first()
    )


def task_binding(connection, owner, account, supplier_key):
    return (
        connection.execute(
            select(bindings).where(
                bindings.c.owner == owner,
                bindings.c.account == account,
                bindings.c.supplier_key == supplier_key,
                bindings.c.enabled.is_(True),
            )
        )
        .mappings()
        .first()
    )


def browse(connection, owner, query):
    table = bindings
    criteria = [table.c.owner == owner]
    columns = [table.c.group_name, table.c.chat_id, table.c.employee, table.c.userid]
    columns.extend([table.c.supplier_name, table.c.supplier_id])
    if query.account:
        criteria.append(table.c.account == query.account)
    if query.status != "all":
        criteria.append(table.c.enabled == (query.status == "enabled"))
    if query.keyword:
        criteria.append(or_(*(column.icontains(query.keyword, autoescape=True) for column in columns)))
    total = connection.execute(select(func.count()).select_from(table).where(*criteria)).scalar_one()
    order = [table.c.account, table.c.supplier_id]
    rows = (
        connection.execute(
            select(table)
            .where(*criteria)
            .order_by(*order)
            .limit(query.pageSize)
            .offset((query.page - 1) * query.pageSize)
        )
        .mappings()
        .all()
    )
    return rows, total


def save(connection, values, revision):
    if revision == 0:
        connection.execute(insert(bindings).values(**values))
        return True
    return (
        connection.execute(
            update(bindings)
            .where(
                bindings.c.owner == values["owner"],
                bindings.c.account == values["account"],
                bindings.c.supplier_id == values["supplier_id"],
                bindings.c.revision == revision,
            )
            .values(**values)
        ).rowcount
        == 1
    )
