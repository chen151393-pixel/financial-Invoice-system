"""identity 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .audit import audit
from .department import department_roles, departments, sync_scopes
from .directory_preview import directory_previews, user_sync_scopes
from .login_flow import login_flows
from .sync_run import sync_runs
from .user import user_departments, user_roles, users

__all__ = [
    "audit",
    "department_roles",
    "departments",
    "directory_previews",
    "user_sync_scopes",
    "login_flows",
    "sync_runs",
    "sync_scopes",
    "user_departments",
    "user_roles",
    "users",
]
