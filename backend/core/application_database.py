"""应用表合入业务库的部署工具；不在启动期间建表、复制或修改状态。"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select

from backend.database import metadata


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


def copy_application_records(source_engine, target_engine, expected_version):
    """同主键同内容可重跑；冲突整笔回滚，保留源库和目标库既有记录。"""
    with source_engine.connect() as source, target_engine.begin() as target:
        if source.dialect.name == "sqlite":
            source.exec_driver_sql("BEGIN")
        for connection in (source, target):
            names = set(inspect(connection).get_table_names())
            if not set(metadata.tables) <= names or "alembic_version" not in names:
                raise RuntimeError("历史库或目标库缺少应用表，请先核对迁移版本")
            version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
            if version != expected_version:
                raise RuntimeError("历史库和目标库须先核对到当前应用迁移版本")
        results = {}
        for table in metadata.sorted_tables:
            keys = tuple(column.name for column in table.primary_key)
            existing = {
                tuple(row[name] for name in keys): dict(row)
                for row in target.execute(select(table).with_for_update()).mappings()
            }
            pending, total, reused = [], 0, 0
            for row in source.execute(select(table)).mappings():
                values = dict(row)
                identity = tuple(values[name] for name in keys)
                total += 1
                if identity in existing:
                    if existing[identity] != values:
                        raise RuntimeError(f"{table.name} 存在同主键不同内容，迁移已回滚，请人工核对")
                    reused += 1
                else:
                    pending.append(values)
            for offset in range(0, len(pending), 200):
                target.execute(table.insert(), pending[offset : offset + 200])
            results[table.name] = {"source": total, "inserted": len(pending), "reused": reused}
        # 检查写入后的完整源记录，包含快照、旧PDF、审计、executing/unknown及其锁。
        for table in metadata.sorted_tables:
            keys = tuple(column.name for column in table.primary_key)
            actual = {
                tuple(row[name] for name in keys): dict(row)
                for row in target.execute(select(table)).mappings()
            }
            for row in source.execute(select(table)).mappings():
                if actual.get(tuple(row[name] for name in keys)) != dict(row):
                    raise RuntimeError(f"{table.name} 内容核验失败，迁移已回滚")
        return results
