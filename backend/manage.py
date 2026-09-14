import argparse
import json

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from .config import ROOT, load_settings
from .core.business_database import check_business_database, make_business_engine
from .database import make_engine
from .workflow import Workflow


def migration_head():
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


def verify_database(engine):
    """启动时只核对迁移版本，不修改表或任务状态。"""
    with engine.connect() as connection:
        if "alembic_version" not in inspect(connection).get_table_names():
            raise RuntimeError("请先运行 python -m backend.manage upgrade 初始化数据库")
        if connection.execute(text("SELECT version_num FROM alembic_version")).scalar() != migration_head():
            raise RuntimeError("数据库版本不匹配，请运行 python -m backend.manage upgrade")


def upgrade(database_url, sql=False):
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head", sql=sql)


def main():
    parser = argparse.ArgumentParser(description="NS 数据库迁移与离线恢复")
    parser.add_argument("command", choices=["upgrade", "mysql-sql", "recover", "business-check"])
    parser.add_argument("--services-stopped", action="store_true", help="明确确认所有 API/任务进程已停止")
    args = parser.parse_args()
    if args.command == "mysql-sql":
        upgrade("mysql+pymysql://unused@localhost/unused?charset=utf8mb4", sql=True)
        return
    settings = load_settings()
    if args.command == "business-check":
        engine = make_business_engine(settings.business_database_url)
        try:
            result = check_business_database(engine)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ready"] else 1)
        finally:
            if engine is not None:
                engine.dispose()
    if args.command == "upgrade":
        upgrade(settings.database_url)
        print("数据库迁移完成")
    else:
        if not args.services_stopped:
            parser.error("recover 仅能在所有 API/任务进程停止后执行，请传 --services-stopped")
        engine = make_engine(settings.database_url)
        try:
            count = Workflow(settings, None, engine).recover_interrupted()
            print(f"已标记 {count} 个中断任务为 unknown；须人工核对 NS，不会再次提交")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
