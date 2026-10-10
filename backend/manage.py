"""数据库部署与版本核验；正常启动不执行迁移。

迁移分两部分：
- 新迁移链 `backend/migrations`（版本表 `schema_version`）：按 docs/architecture/database.md 建立的新表结构。
- 旧迁移链 `backend/legacy_migrations`（版本表 `alembic_version`、`business_alembic_version`）：
  旧模块在架构第 4 步重建前仍在使用，随各模块切换删除。
"""

import argparse
import json

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .core.config import ROOT, load_settings
from .core.database import check_business_database, make_business_engine
from .legacy_migrations.bootstrap import bootstrap_application_tables

SCHEMA_INI = ROOT / "backend" / "alembic.ini"
LEGACY_APP_INI = ROOT / "backend" / "legacy_migrations" / "app.ini"
LEGACY_BUSINESS_INI = ROOT / "backend" / "legacy_migrations" / "business.ini"
OFFLINE_MYSQL_URL = "mysql+pymysql://unused@localhost/unused?charset=utf8mb4"


def _config(path, database_url):
    config = Config(str(path))
    config.attributes["database_url"] = database_url
    return config


def _head(path):
    return ScriptDirectory.from_config(Config(str(path))).get_current_head()


def migration_head():
    """旧应用迁移链的最新版本（旧测试与旧启动核验使用）。"""
    return _head(LEGACY_APP_INI)


def schema_head():
    return _head(SCHEMA_INI)


def _version(connection, table):
    if table not in inspect(connection).get_table_names():
        return None
    return connection.execute(text(f"SELECT version_num FROM {table}")).scalar()


def verify_database(engine, *, business=False):
    """启动时只核对迁移版本，不修改表或任务状态。"""
    with engine.connect() as connection:
        version = _version(connection, "alembic_version")
        if version is None:
            raise RuntimeError("请先运行 python -m backend.manage upgrade 初始化数据库")
        if version != migration_head():
            raise RuntimeError("数据库版本不匹配，请运行 python -m backend.manage upgrade")
        if business:
            version = _version(connection, "business_alembic_version")
            if version is None:
                raise RuntimeError("业务迁移版本缺失，请运行 python -m backend.manage upgrade")
            if version != _head(LEGACY_BUSINESS_INI):
                raise RuntimeError("业务迁移版本不匹配，请运行 python -m backend.manage upgrade")
            if _version(connection, "schema_version") != schema_head():
                raise RuntimeError("新表结构版本不匹配，请运行 python -m backend.manage upgrade")


def upgrade_schema(database_url, sql=False):
    """新迁移链：只创建或修改新表，不读写旧表。"""
    if not database_url:
        raise ValueError("尚未配置业务MySQL，不能执行迁移")
    command.upgrade(_config(SCHEMA_INI, database_url), "head", sql=sql)


def upgrade(database_url, sql=False):
    """旧应用迁移链；隔离测试与旧模块使用。"""
    command.upgrade(_config(LEGACY_APP_INI, database_url), "head", sql=sql)


def upgrade_business(database_url, sql=False):
    """旧业务迁移链；历史版本不重写。"""
    if not database_url:
        raise ValueError("尚未配置业务MySQL，不能执行迁移")
    command.upgrade(_config(LEGACY_BUSINESS_INI, database_url), "head", sql=sql)


def upgrade_unified(database_url):
    """同一业务库：先升级两条旧迁移链（旧模块仍在使用），再升级新迁移链。"""
    engine = make_business_engine(database_url)
    if engine is None:
        raise ValueError("请先配置业务MySQL，统一升级不使用旧DATABASE_URL")
    try:
        result = check_business_database(engine)
        if not result["ready"]:
            raise RuntimeError(result["message"])
        upgrade_business(database_url)
        if bootstrap_application_tables(engine):
            command.stamp(_config(LEGACY_APP_INI, database_url), "head")
        else:
            upgrade(database_url)
        upgrade_schema(database_url)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="业务库迁移与版本核验")
    parser.add_argument(
        "command",
        choices=["upgrade", "schema-sql", "mysql-sql", "business-check", "business-upgrade", "business-sql"],
        help="upgrade：升级全部迁移链；schema-sql：输出新表结构的 MySQL DDL 供审阅",
    )
    args = parser.parse_args()
    if args.command == "schema-sql":
        upgrade_schema(OFFLINE_MYSQL_URL, sql=True)
        return
    if args.command == "mysql-sql":
        upgrade(OFFLINE_MYSQL_URL, sql=True)
        return
    if args.command == "business-sql":
        upgrade_business(OFFLINE_MYSQL_URL, sql=True)
        return
    settings = load_settings()
    if args.command in ("upgrade", "business-upgrade"):
        upgrade_unified(settings.business_database_url)
        print("业务库全部迁移链升级完成，未拉取或写回NS")
        return
    if args.command == "business-check":
        engine = make_business_engine(settings.business_database_url)
        try:
            result = check_business_database(engine)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ready"] else 1)
        finally:
            if engine is not None:
                engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError:
        raise SystemExit("数据库操作失败，请检查连接、权限及结构；错误详情不输出凭据") from None
