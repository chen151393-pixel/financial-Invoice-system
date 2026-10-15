"""MySQL 命名锁：覆盖"读取外部数据 → 保存"全过程；SQLite（隔离测试）为单连接，不加锁。"""

from sqlalchemy import text


def _mysql(connection):
    return connection.dialect.name == "mysql"


def acquire(connection, name):
    if not _mysql(connection):
        return True
    return connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": name}).scalar() == 1


def owns(connection, name):
    if not _mysql(connection):
        return True
    return (
        connection.execute(text("SELECT IS_USED_LOCK(:name) = CONNECTION_ID()"), {"name": name}).scalar() == 1
    )


def release(connection, name):
    if _mysql(connection):
        connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
