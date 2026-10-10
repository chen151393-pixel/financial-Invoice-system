"""旧应用表在业务库中的首次建表（过渡期使用，随架构第 4 步旧迁移链一并删除）。"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from backend.database import metadata
from sqlalchemy import inspect


def schema_changes(connection):
    """仅比较应用表，保留采购、报关、发票及其他既有业务表。"""

    def include_object(obj, name, kind, reflected, compare_to):
        return not (kind == "table" and reflected and name not in metadata.tables)

    changes = compare_metadata(
        MigrationContext.configure(connection, opts={"include_object": include_object}), metadata
    )
    # 已有中文注释不影响结构兼容；保留数据库注释，不为接管而清除它们。
    structural = []
    for change in changes:
        if isinstance(change, list):
            items = [item for item in change if item[0] != "modify_comment"]
            if items:
                structural.append(items)
        elif change[0] not in {"add_table_comment", "remove_table_comment"}:
            structural.append(change)
    return structural


def verify_application_keys(connection, names):
    """Alembic比较之外核对主键及MySQL存储引擎，避免错误接管历史表。"""
    inspector = inspect(connection)
    for name in names:
        table = metadata.tables[name]
        expected = [column.name for column in table.primary_key]
        if inspector.get_pk_constraint(name)["constrained_columns"] != expected:
            raise RuntimeError("已有应用表主键不一致，未登记迁移版本")
        if connection.dialect.name == "mysql":
            options = inspector.get_table_options(name)
            if options.get("mysql_engine", "").lower() != "innodb":
                raise RuntimeError("应用表须使用InnoDB事务引擎，未登记迁移版本")


def bootstrap_application_tables(engine):
    """允许采用已存在的供应商群表；完整核验最终结构后才登记迁移版本。"""
    with engine.connect() as connection:
        names = set(inspect(connection).get_table_names())
        if "alembic_version" in names:
            return False
        existing = names & set(metadata.tables)
        if existing - {"finance_supplier_groups"}:
            raise RuntimeError("发现未登记迁移版本的应用表，请先核实历史结构，不能自动接管")
        verify_application_keys(connection, existing)
        changes = schema_changes(connection)

        def adds_missing_object(change):
            if change[0] == "add_table":
                return change[1].name not in existing
            if change[0] == "add_index":
                return change[1].table.name not in existing
            return False

        if any(not adds_missing_object(change) for change in changes):
            raise RuntimeError("已有供应商群表与应用表定义不一致，未修改结构或登记版本")
        # 仅部署命令调用；检查过的现有表和数据保持原样。
        metadata.create_all(connection)
        verify_application_keys(connection, set(metadata.tables))
        if schema_changes(connection):
            raise RuntimeError("应用表最终结构核验失败，未登记迁移版本")
        connection.commit()
    return True
