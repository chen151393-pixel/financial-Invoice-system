"""反射用户已迁移的两表，不自动建表或执行迁移。"""

from sqlalchemy import MetaData, Table

from backend.core.errors import ApiError

from .parser import HEAD_MAP, LINE_MAP


def load_tables(connection):
    metadata = MetaData()
    head = Table("invoices", metadata, autoload_with=connection)
    lines = Table("invoice_lines", metadata, autoload_with=connection)
    required = set(HEAD_MAP.values()) | {
        "id",
        "tenant_id",
        "external_system",
        "external_account",
        "import_key",
        "source_data",
        "content_hash",
        "source_version",
        "invoice_direction",
        "invoice_status",
        "validation_status",
        "validation_errors",
        "created_at",
        "updated_at",
        "synced_at",
        "last_complete_sync_at",
        "detail_sync_status",
        "is_active",
    }
    line_required = set(LINE_MAP.values()) | {
        "id",
        "tenant_id",
        "invoice_id",
        "source_line_key",
        "line_no",
        "tax_rate",
        "tax_treatment",
        "amount_including_tax",
        "synced_at",
        "is_active",
    }
    if not required <= set(head.c.keys()) or not line_required <= set(lines.c.keys()):
        raise ApiError(503, "发票表缺少导入字段，请先核对发票Excel扩展SQL")
    if getattr(lines.c.quantity.type, "scale", 0) < 8:
        raise ApiError(503, "发票明细数量精度不足，请先扩展为DECIMAL(26,8)")
    return head, lines
