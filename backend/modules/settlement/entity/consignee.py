"""结汇客户名称：同一规范化匹配键只登记一个展示原名。"""

from sqlalchemy import Column, String, Table

from backend.core.schema import identifier, schema_metadata, table_options, timestamps

settlement_consignees = Table(
    "settlement_consignees",
    schema_metadata,
    Column("name_key", identifier(500), primary_key=True, comment="去符号、空白并统一大写后的客户匹配键"),
    Column("display_name", String(500), nullable=False, comment="首次登记的客户原名；后续格式变体不覆盖"),
    *timestamps(),
    comment="结汇客户名称归并；香港客户展示由环境配置覆盖",
    **table_options,
)
