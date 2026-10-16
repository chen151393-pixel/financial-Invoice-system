"""已有账号绑定记录；不存密码、授权码或令牌。"""

from sqlalchemy import CheckConstraint, Column, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

lemon_bindings = Table(
    "sync_lemon_bindings",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="绑定记录主键"),
    Column("scope_key", identifier(64), nullable=False, comment="环境、应用与操作身份的摘要"),
    Column("owner", identifier(190), nullable=False, comment="发起绑定的认证身份"),
    Column("mobile", identifier(32), nullable=False, comment="绑定的已有账号手机号"),
    Column("status", identifier(20), nullable=False, comment="未绑定、绑定中、结果未知或已绑定"),
    Column("verified_at", TIMESTAMP, nullable=True, comment="最近确认绑定成功时间，UTC"),
    Column("selected_asid", identifier(32), nullable=True, comment="已选择并核实可访问的账套编号"),
    Column("selected_name", identifier(255), nullable=True, comment="已选择账套名称"),
    *timestamps(),
    UniqueConstraint("scope_key", name="uq_sync_lemon_binding_scope"),
    CheckConstraint("status IN ('unbound','binding','unknown','bound')", name="ck_sync_lemon_binding_status"),
    comment="柠檬云已有账号绑定状态，不保存凭据",
    **table_options,
)
