"""数据库部署、版本核验与离线恢复；正常启动不执行迁移。"""

import argparse
import json

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from .core.application_database import bootstrap_application_tables, copy_application_records
from .core.business_database import check_business_database, make_business_engine
from .core.config import ROOT, load_settings
from .database import make_engine


def migration_head():
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


def verify_database(engine, *, business=False):
    """启动时只核对迁移版本，不修改表或任务状态。"""
    with engine.connect() as connection:
        if "alembic_version" not in inspect(connection).get_table_names():
            raise RuntimeError("请先运行 python -m backend.manage upgrade 初始化数据库")
        if connection.execute(text("SELECT version_num FROM alembic_version")).scalar() != migration_head():
            raise RuntimeError("数据库版本不匹配，请运行 python -m backend.manage upgrade")
        if business:
            config = Config(str(ROOT / "backend" / "business_alembic.ini"))
            head = ScriptDirectory.from_config(config).get_current_head()
            if "business_alembic_version" not in inspect(connection).get_table_names():
                raise RuntimeError("业务迁移版本缺失，请运行 python -m backend.manage upgrade")
            version = connection.execute(text("SELECT version_num FROM business_alembic_version")).scalar()
            if version != head:
                raise RuntimeError("业务迁移版本不匹配，请运行 python -m backend.manage upgrade")


def upgrade(database_url, sql=False):
    """保留历史应用迁移及隔离测试入口，正式部署使用upgrade_unified。"""
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head", sql=sql)


def upgrade_business(database_url, sql=False):
    """业务迁移仍保留独立版本表，历史版本不重写。"""
    if not database_url:
        raise ValueError("尚未配置业务MySQL，不能执行迁移")
    config = Config(str(ROOT / "backend" / "business_alembic.ini"))
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head", sql=sql)


def upgrade_unified(database_url):
    """两条历史迁移链登记在同一业务库，不重写已经执行的迁移。"""
    engine = make_business_engine(database_url)
    if engine is None:
        raise ValueError("请先配置业务MySQL，统一升级不使用旧DATABASE_URL")
    try:
        result = check_business_database(engine)
        if not result["ready"]:
            raise RuntimeError(result["message"])
        upgrade_business(database_url)
        if bootstrap_application_tables(engine):
            config = Config(str(ROOT / "backend" / "alembic.ini"))
            config.attributes["database_url"] = database_url
            command.stamp(config, "head")
        else:
            upgrade(database_url)
    finally:
        engine.dispose()


def import_application_database(source_url, target_url):
    """维护窗口中复制旧应用库；源SQLite须已存在，避免误创建空文件。"""
    parsed = make_url(source_url)
    if parsed.drivername == "sqlite":
        file = (ROOT / (parsed.database or "")).resolve()
        if not file.is_file():
            raise ValueError("历史SQLite文件不存在，未执行复制")
        parsed = parsed.set(database=str(file))
    source = make_engine(parsed.render_as_string(hide_password=False))
    target = make_business_engine(target_url)
    if target is None:
        source.dispose()
        raise ValueError("请先配置业务MySQL")
    try:
        if source.url == target.url:
            raise ValueError("历史库与目标业务库不能是同一个连接")
        return copy_application_records(source, target, migration_head())
    finally:
        source.dispose()
        target.dispose()


def main():
    parser = argparse.ArgumentParser(description="统一业务库迁移与离线恢复")
    parser.add_argument(
        "command",
        choices=[
            "upgrade",
            "mysql-sql",
            "business-check",
            "business-upgrade",
            "business-sql",
            "import-application",
        ],
    )
    parser.add_argument("--services-stopped", action="store_true", help="明确确认所有 API/任务进程已停止")
    parser.add_argument("--source-database-url", help="显式指定历史应用库，仅供import-application")
    args = parser.parse_args()
    if args.command == "mysql-sql":
        upgrade("mysql+pymysql://unused@localhost/unused?charset=utf8mb4", sql=True)
        return
    if args.command == "business-sql":
        upgrade_business("mysql+pymysql://unused@localhost/unused?charset=utf8mb4", sql=True)
        return
    settings = load_settings()
    if args.command == "import-application":
        if not args.services_stopped or not args.source_database_url:
            parser.error("复制历史数据须停止全部API/任务进程，提供--services-stopped及--source-database-url")
        result = import_application_database(args.source_database_url, settings.business_database_url)
        print(json.dumps(result, ensure_ascii=False))
        return
    if args.command in ("upgrade", "business-upgrade"):
        upgrade_unified(settings.business_database_url)
        print("统一业务库两条迁移链升级完成，未拉取或写回NS")
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
