"""审核记录：一次审核通过一行，不可修改，全部行即审核历史。"""

from sqlalchemy import CHAR, CheckConstraint, Column, Computed, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

records = Table(
    "review_records",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column("ns_account", String(100), comment="NS 账套标识，用于隔离正式、沙箱等来源", nullable=False),
    Column(
        "customs_declaration_id",
        ID,
        nullable=False,
        comment="报关单本地主键，指向 source_customs_declarations.id",
    ),
    Column("record_no", String(150), comment="NS 报关记录的 CD 编号，与真实海关报关单号不同"),
    Column("revision", Integer, nullable=False, comment="同一业务对象的递增版本号；具体对象见唯一约束"),
    Column("content_sha256", CHAR(64), nullable=False, comment="本次审核看到的报关单与关联子采购内容摘要"),
    Column(
        "status",
        String(24),
        comment="审核记录状态：active 当前记录；superseded 已替代；仍须核对来源变化",
        nullable=False,
        server_default="active",
    ),
    Column("approved_by", String(200), comment="审核通过的认证操作者", nullable=False),
    Column("approved_at", TIMESTAMP, comment="审核通过时间，UTC", nullable=False),
    Column("note", String(300), comment="人工备注或登记说明，具体长度见类型"),
    Column(
        "active_declaration_id",
        ID,
        Computed("CASE WHEN status = 'active' THEN customs_declaration_id END", persisted=True),
        comment="自动生成：active 审核取报关单 ID，否则为空；保证每张报关单最多一条 active 记录",
    ),
    *timestamps(),
    UniqueConstraint("customs_declaration_id", "revision", name="uq_review_revision"),
    UniqueConstraint("active_declaration_id", name="uq_review_active"),
    CheckConstraint("status IN ('active','superseded')", name="ck_review_status"),
    comment="审核记录：一次审核通过一行，不可修改，全部行即审核历史",
    **table_options,
)
