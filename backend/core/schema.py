"""统一元数据与跨数据库字段类型。"""

from sqlalchemy import MetaData, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR

metadata = MetaData()


def identifier(length):
    return String(length).with_variant(VARCHAR(length, collation="utf8mb4_bin"), "mysql")


document = Text().with_variant(LONGTEXT(), "mysql")
table_options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
