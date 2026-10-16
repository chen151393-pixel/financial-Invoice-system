"""新迁移链的版本表：容纳完整版本名，并兼容已经创建的短字段。"""

from alembic.ddl.mysql import MySQLImpl
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import String, inspect

VERSION_TABLE = "schema_version"
VERSION_LENGTH = 128


class SchemaMySQLImpl(MySQLImpl):
    __dialect__ = "mysql"

    def version_table_impl(self, *, version_table, **kwargs):
        table = super().version_table_impl(version_table=version_table, **kwargs)
        # 只扩展新迁移链；旧链继续使用原有结构和版本标识。
        if version_table == VERSION_TABLE:
            table.c.version_num.type = String(VERSION_LENGTH)
        return table


def widen_schema_version(connection):
    """调用方持有迁移锁后扩宽已有字段；保留版本值、主键、排序规则和空值约束。"""
    if connection.dialect.name != "mysql":
        return
    inspector = inspect(connection)
    if not inspector.has_table(VERSION_TABLE):
        return
    column = next(item for item in inspector.get_columns(VERSION_TABLE) if item["name"] == "version_num")
    length = getattr(column["type"], "length", None)
    if length is None or length >= VERSION_LENGTH:
        return
    operations = Operations(MigrationContext.configure(connection))
    operations.alter_column(
        VERSION_TABLE,
        "version_num",
        type_=String(VERSION_LENGTH, collation=column["type"].collation),
        existing_type=column["type"],
        existing_nullable=column["nullable"],
    )
