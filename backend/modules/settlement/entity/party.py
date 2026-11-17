"""合同抬头：买卖双方的中英文名称、地址、电话与印章图片，供销售合同模板取用。

name 为匹配用名称：买方与海关回执的境外收货人一致，卖方为境内发货人名称；name_key 为规范化后的唯一键。
印章图片保存在结汇资料目录，本表只记录文件标识与校验值。
"""

from sqlalchemy import CHAR, Column, String, Table, UniqueConstraint

from backend.core.schema import ID, identifier, schema_metadata, table_options, timestamps

settlement_parties = Table(
    "settlement_parties",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="合同抬头本地主键"),
    Column("name", String(300), nullable=False, comment="匹配用名称；买方须与海关回执境外收货人一致"),
    Column("name_key", identifier(300), nullable=False, comment="名称规范化键（去空白、小写），唯一"),
    Column("name_cn", String(255), comment="合同上的中文名称"),
    Column("name_en", String(255), nullable=False, comment="合同上的英文名称"),
    Column("address_cn", String(500), comment="中文地址"),
    Column("address_en", String(500), nullable=False, comment="英文地址"),
    Column("phone", String(100), comment="电话"),
    Column("stamp_file_id", identifier(36), comment="印章图片文件标识；未上传为空"),
    Column("stamp_sha256", CHAR(64), comment="印章图片 SHA-256"),
    Column("stamp_extension", String(10), comment="印章图片扩展名：png 或 jpg"),
    Column("updated_by", String(190), nullable=False, comment="最近维护人（认证身份）"),
    *timestamps(),
    UniqueConstraint("name_key", name="uq_settlement_party_name_key"),
    comment="销售合同买卖双方抬头与印章",
    **table_options,
)
