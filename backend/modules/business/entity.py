"""复用已建的四张业务表；只反射结构，不注册迁移、不自动建表。"""

from sqlalchemy import MetaData, Table

TABLE_NAMES = ("purchase_orders", "purchase_order_lines", "customs_declarations", "customs_declaration_lines")
STORAGE_FIELDS = {
    "purchase": {
        "order_no",
        "order_date",
        "parent_order_no",
        "supplier_identifier",
        "supplier_name",
        "currency_code",
        "total_amount",
        "source_modified_at",
    },
    "purchase_line": {
        "line_no",
        "item_code",
        "item_name",
        "declaration_name",
        "specification",
        "quantity",
        "unit_name",
        "declaration_quantity",
        "declaration_unit",
        "tax_inclusive_price",
        "amount",
    },
    "customs": {
        "record_no",
        "declaration_no",
        "declaration_date",
        "declarant_identifier",
        "declarant_name",
        "source_modified_at",
    },
    "customs_line": {
        "line_no",
        "sales_order_no",
        "origin_place",
        "item_code",
        "declaration_name",
        "specification",
        "quantity",
        "unit_name",
        "declared_quantity",
        "declared_unit",
        "unit_price",
        "amount",
        "currency_code",
    },
}
REQUIRED_FIELDS = {
    "purchase": {"order_no"},
    "purchase_line": {"declaration_name", "quantity", "unit_name", "amount"},
    "customs": {"declaration_no", "declaration_date"},
    "customs_line": {"declaration_name", "specification", "origin_place", "quantity", "unit_name"},
}


def load_tables(connection):
    metadata = MetaData()
    return {name: Table(name, metadata, autoload_with=connection) for name in TABLE_NAMES}
