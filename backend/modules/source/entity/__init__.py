"""source 模块拥有的表；导入本包即把全部表登记到 schema_metadata。"""

from .company import companies
from .customs_declaration import customs_declarations
from .customs_line import customs_lines
from .customs_purchase_link import customs_purchase_links
from .parent_order import parent_orders
from .parent_order_line import parent_order_lines
from .purchase_order import purchase_orders
from .purchase_order_line import purchase_order_lines
from .raw_record import raw_records
from .supplier import suppliers

__all__ = [
    "companies",
    "customs_declarations",
    "customs_lines",
    "customs_purchase_links",
    "parent_order_lines",
    "parent_orders",
    "purchase_order_lines",
    "purchase_orders",
    "raw_records",
    "suppliers",
]
