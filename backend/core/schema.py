"""统一元数据与跨数据库字段类型。"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, LONGTEXT, VARCHAR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

metadata = MetaData()
# 新表结构（docs/architecture/database.md）的表定义登记在独立元数据中，不与旧表元数据混用；
# 旧迁移链的建表核验只比较旧元数据。
schema_metadata = MetaData()


def identifier(length):
    return String(length).with_variant(VARCHAR(length, collation="utf8mb4_bin"), "mysql")


document = Text().with_variant(LONGTEXT(), "mysql")
table_options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}

# 新表结构（docs/architecture/database.md）的通用列类型。
# 主键与引用：MySQL 为 BIGINT UNSIGNED；SQLite 只有 INTEGER PRIMARY KEY 才会自增，测试库用 INTEGER。
ID = BigInteger().with_variant(BIGINT(unsigned=True), "mysql").with_variant(Integer(), "sqlite")
# 时间：MySQL DATETIME(6)，统一存 UTC（MySQL 连接已设置 time_zone='+00:00'）。
TIMESTAMP = DateTime().with_variant(DATETIME(fsp=6), "mysql")


class utc_now(FunctionElement):
    """created_at / updated_at 的数据库默认值；精度须与 DATETIME(6) 一致。"""

    type = DateTime()
    inherit_cache = True


@compiles(utc_now)
def _utc_now_default(element, compiler, **kw):
    return "CURRENT_TIMESTAMP"


@compiles(utc_now, "mysql")
def _utc_now_mysql(element, compiler, **kw):
    return "CURRENT_TIMESTAMP(6)"


def timestamps():
    """新表公共列：created_at、updated_at（UTC）；updated_at 由 DAO 在每次更新时写入。"""
    return [
        Column("created_at", TIMESTAMP, nullable=False, server_default=utc_now()),
        Column("updated_at", TIMESTAMP, nullable=False, server_default=utc_now()),
    ]
