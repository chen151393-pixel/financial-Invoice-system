"""task 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .document import documents
from .event import events
from .notification import notifications
from .supplier_group import supplier_groups
from .task import tasks
from .task_line import task_lines

__all__ = ["documents", "events", "notifications", "supplier_groups", "task_lines", "tasks"]
