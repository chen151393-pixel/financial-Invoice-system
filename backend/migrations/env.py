"""新表结构迁移链（docs/architecture/database.md），版本表 schema_version。

只创建或修改新表，不读写旧表。正式环境为业务 MySQL；SQLite 仅供隔离测试。
"""

import hashlib

from alembic import context
from backend.core.config import load_settings
from backend.core.database import make_business_engine, make_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url

VERSION_TABLE = "schema_version"

config = context.config
database_url = config.attributes.get("database_url") or load_settings().business_database_url
if not database_url:
    raise RuntimeError("请配置 BUSINESS_DATABASE_URL 或 BUSINESS_MYSQL_*，或显式指定迁移连接")

if context.is_offline_mode():
    context.configure(
        url=database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    mysql = make_url(database_url).drivername == "mysql+pymysql"
    engine = make_business_engine(database_url) if mysql else make_engine(database_url)
    try:
        with engine.connect() as connection:
            lock = None
            if mysql:
                # 同一库同时只运行一次迁移命令。
                database = connection.execute(text("SELECT DATABASE()")).scalar_one()
                lock = hashlib.sha256(f"schema:{database}".encode()).hexdigest()
                if connection.execute(text("SELECT GET_LOCK(:key, 0)"), {"key": lock}).scalar_one() != 1:
                    raise RuntimeError("已有迁移正在执行，请稍后重试")
                connection.commit()
            try:
                context.configure(connection=connection, version_table=VERSION_TABLE)
                with context.begin_transaction():
                    context.run_migrations()
                connection.commit()
            finally:
                if lock:
                    connection.execute(text("SELECT RELEASE_LOCK(:key)"), {"key": lock})
    finally:
        engine.dispose()
