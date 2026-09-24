"""默认反射采购报关四表，关联导入按需增加母采购两表；不自动建表。"""

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


def load_tables(connection, *, include_parents=False, include_relations=False):
    metadata = MetaData()
    names = TABLE_NAMES + (
        ("parent_purchase_orders", "parent_purchase_order_lines") if include_parents else ()
    )
    if include_relations:
        names += ("customs_reconciliation_results",)
    return {name: Table(name, metadata, autoload_with=connection) for name in names}
