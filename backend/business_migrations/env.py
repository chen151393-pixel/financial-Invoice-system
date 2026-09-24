"""独立业务库的增量迁移，不读取或修改应用库。"""

import hashlib

from alembic import context
from backend.core.business_database import make_business_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url

config = context.config
database_url = config.attributes.get("database_url")
if not database_url or make_url(database_url).drivername != "mysql+pymysql":
    raise RuntimeError("业务迁移须显式指定独立 MySQL 业务库")

if context.is_offline_mode():
    context.configure(
        url=database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="business_alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_business_engine(database_url)
    try:
        with engine.connect() as connection:
            # 只协调迁移命令；不借此宣称业务写请求已经停止。
            database = connection.execute(text("SELECT DATABASE()")).scalar_one()
            lock = hashlib.sha256(f"business-schema:{database}".encode()).hexdigest()
            if connection.execute(text("SELECT GET_LOCK(:key, 0)"), {"key": lock}).scalar_one() != 1:
                raise RuntimeError("已有业务库迁移正在执行，请稍后重试")
            connection.commit()
            try:
                context.configure(connection=connection, version_table="business_alembic_version")
                with context.begin_transaction():
                    context.run_migrations()
                connection.commit()
            finally:
                connection.execute(text("SELECT RELEASE_LOCK(:key)"), {"key": lock})
                connection.commit()
    finally:
        engine.dispose()
