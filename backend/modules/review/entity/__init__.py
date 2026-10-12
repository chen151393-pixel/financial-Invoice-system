"""review 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .line import lines
from .record import records

__all__ = ["lines", "records"]
