"""task 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .document import documents
from .event import events
from .notification import notifications
from .supplier_group import supplier_groups
from .task import tasks
from .task_line import task_lines

__all__ = ["documents", "events", "notifications", "supplier_groups", "task_lines", "tasks"]

from .contract_job import contract_jobs as contract_jobs
from .declaration_document import declaration_documents as declaration_documents
from .external_group import external_groups as external_groups
from .group_import import group_imports as group_imports
from .notification_delivery import deliveries as deliveries
from .notification_group_guard import notification_group_guards as notification_group_guards
from .signed_contract import signed_contracts as signed_contracts
from .signed_upload_job import signed_upload_jobs as signed_upload_jobs
from .supplier_setting import supplier_settings as supplier_settings
