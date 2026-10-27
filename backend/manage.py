"""新表迁移与启动核验；只操作 schema_version 迁移链，不修改旧表。"""

import argparse
import json

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .core.config import ROOT, load_settings
from .core.database import check_business_database, make_business_engine

SCHEMA_INI = ROOT / "backend" / "alembic.ini"
OFFLINE_MYSQL_URL = "mysql+pymysql://unused@localhost/unused?charset=utf8mb4"


def _config(path, database_url):
    config = Config(str(path))
    config.attributes["database_url"] = database_url
    return config


def _head(path):
    return ScriptDirectory.from_config(Config(str(path))).get_current_head()


def schema_head():
    return _head(SCHEMA_INI)


def _version(connection, table):
    if table not in inspect(connection).get_table_names():
        return None
    return connection.execute(text(f"SELECT version_num FROM {table}")).scalar()


def verify_database(engine):
    """启动只核验版本；不自动建表、清除状态或释放业务锁。"""
    with engine.connect() as connection:
        if _version(connection, "schema_version") != schema_head():
            raise RuntimeError("数据库版本不匹配，请运行 python -m backend.manage upgrade")


def upgrade_schema(database_url, sql=False):
    """新迁移链：只创建或修改新表，不读写旧表。"""
    if not database_url:
        raise ValueError("尚未配置业务MySQL，不能执行迁移")
    command.upgrade(_config(SCHEMA_INI, database_url), "head", sql=sql)


def upgrade_unified(database_url):
    engine = make_business_engine(database_url)
    if engine is None:
        raise ValueError("请先配置业务 MySQL")
    try:
        result = check_business_database(engine, tables=())
        if not result["connected"]:
            raise RuntimeError(result["message"])
        upgrade_schema(database_url)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="业务库迁移与版本核验")
    parser.add_argument(
        "command",
        choices=[
            "upgrade",
            "schema-sql",
            "mysql-sql",
            "business-check",
            "business-upgrade",
            "business-sql",
            "rebuild-ledger",
            "rebuild-review",
            "schema-map",
        ],
        help="upgrade：升级新迁移链；schema-sql：仅输出结构 DDL 供审阅，不能代替在线数据升级；"
        "schema-map：重新生成 docs/mysql/schema-map.md 表与迁移对照，不连接数据库",
    )
    args = parser.parse_args()
    if args.command in ("schema-sql", "mysql-sql", "business-sql"):
        upgrade_schema(OFFLINE_MYSQL_URL, sql=True)
        return
    if args.command == "schema-map":
        from .migrations.schema_map import write

        print(f"已生成 {write().relative_to(ROOT).as_posix()}")
        return
    settings = load_settings()
    if args.command == "rebuild-review":
        from .core.events import EventBus
        from .modules.review.service.calculation_service import CalculationService
        from .modules.review.service.review_service import ReviewService
        from .modules.source.public import DeclarationService

        engine = make_business_engine(settings.business_database_url)
        if engine is None:
            raise ValueError("请先配置业务 MySQL")
        try:
            verify_database(engine)
            service = ReviewService(
                engine, DeclarationService(engine), EventBus(), settings.review_unit_price_tolerance_cny
            )
            count = CalculationService(service).rebuild()
            print(f"财务审核查询快照补算完成：{count} 个账套；未调用 NS、未写入审核记录")
        finally:
            engine.dispose()
        return
    if args.command == "rebuild-ledger":
        from .app import create_events
        from .modules.matching.service.rebuild_service import rebuild

        engine = make_business_engine(settings.business_database_url)
        if engine is None:
            raise ValueError("请先配置业务 MySQL")
        try:
            verify_database(engine)
            print(f"已从持久台账核对 {rebuild(engine, create_events())} 条有效任务行；没有自动核实待复核占用")
        finally:
            engine.dispose()
        return
    if args.command in ("upgrade", "business-upgrade"):
        upgrade_unified(settings.business_database_url)
        print("业务库新迁移链升级完成，未拉取或写回NS")
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
