"""task 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .document import documents
from .event import events
from .notification import notifications
from .supplier_group import supplier_groups
from .task import tasks
from .task_line import task_lines

__all__ = ["documents", "events", "notifications", "supplier_groups", "task_lines", "tasks"]

from .contract_job import contract_jobs as contract_jobs
from .external_group import external_groups as external_groups
from .group_import import group_imports as group_imports
from .notification_delivery import deliveries as deliveries
from .notification_group_guard import notification_group_guards as notification_group_guards
