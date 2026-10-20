"""新表结构迁移链（docs/architecture/database.md），版本表 schema_version。

只创建或修改新表，不读写旧表。正式环境为业务 MySQL；SQLite 仅供隔离测试。
"""

import hashlib

from alembic import context
from backend.core.config import load_settings
from backend.core.database import make_business_engine, make_engine
from backend.migrations.version_table import VERSION_TABLE, widen_schema_version
from sqlalchemy import text
from sqlalchemy.engine import make_url

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
            else:
                # SQLite 批量改表要重建被引用的表（删旧表即违反外键）；迁移期间关闭外键，提交前整体复核。
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.commit()
            try:
                widen_schema_version(connection)
                context.configure(connection=connection, version_table=VERSION_TABLE)
                with context.begin_transaction():
                    context.run_migrations()
                    if not mysql:
                        orphans = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                        if orphans:
                            raise RuntimeError(f"迁移后存在外键孤儿行，已回滚：{orphans[:5]}")
                connection.commit()
            finally:
                if lock:
                    connection.execute(text("SELECT RELEASE_LOCK(:key)"), {"key": lock})
                if not mysql:
                    connection.rollback()
                    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                    connection.commit()
    finally:
        engine.dispose()
