"""matching 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .allocation import allocations
from .invoice_file import invoice_files

__all__ = ["allocations", "invoice_files"]
