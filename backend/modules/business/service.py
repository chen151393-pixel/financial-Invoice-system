"""NS 业务来源用例装配：采购报关联查与本地来源存储。"""

from .pl_script_service import PlScriptService
from .storage_service import StorageService


class BusinessService:
    def __init__(self, ns, database_engine=None):
        self.ns = ns
        self.database_engine = database_engine
        self.pl_script = PlScriptService(ns)
        self.storage = StorageService(ns, database_engine)
