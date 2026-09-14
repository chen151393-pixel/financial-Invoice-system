"""数据库连接工厂；不包含业务表与业务SQL。"""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url


def make_engine(database_url):
    url = make_url(database_url)
    if url.drivername not in ("sqlite", "mysql+pymysql"):
        raise ValueError("数据库仅支持 MySQL 8.0 / PyMySQL 或本地 SQLite")
    if url.drivername == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url, connect_args={"check_same_thread": False, "timeout": 10}, hide_parameters=True
        )

        @event.listens_for(engine, "connect")
        def setup_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")

        return engine
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        hide_parameters=True,
        connect_args={"connect_timeout": 10, "read_timeout": 30, "write_timeout": 30},
        isolation_level="READ COMMITTED",
    )
