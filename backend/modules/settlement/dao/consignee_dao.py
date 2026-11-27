"""结汇客户名称读写；唯一键冲突时保留已有原名，不提交事务。"""

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..entity.consignee import settlement_consignees as consignees


def names(connection):
    return dict(connection.execute(select(consignees.c.name_key, consignees.c.display_name)).all())


def add_missing(connection, rows):
    if not rows:
        return
    if connection.dialect.name == "mysql":
        statement = mysql_insert(consignees).on_duplicate_key_update(name_key=consignees.c.name_key)
    else:
        statement = sqlite_insert(consignees).on_conflict_do_nothing(index_elements=["name_key"])
    connection.execute(statement, rows)
