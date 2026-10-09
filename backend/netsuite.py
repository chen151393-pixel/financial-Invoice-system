"""旧NS导入兼容入口；新代码使用integrations.netsuite。"""

from .core.errors import ApiError as ApiError
from .integrations.netsuite.auth import assertion as assertion
from .integrations.netsuite.client import NetSuite as NetSuite
