"""NS业务记录只读用例；后续标准化与持久化在本模块扩展。"""

from backend.core.business_database import check_business_database
from backend.core.errors import ApiError

from .pl_comparison_service import PlComparisonService
from .pl_service import PlLookupService
from .storage_service import StorageService


class BusinessService:
    def __init__(self, ns, database_engine=None):
        self.ns = ns
        self.database_engine = database_engine
        self.pl_lookup = PlLookupService(ns)
        self.pl_comparison = PlComparisonService(ns)
        self.storage = StorageService(ns, database_engine)

    def database_status(self):
        return check_business_database(self.database_engine)

    def records(self, record_type, record_id=None):
        if record_id == "":
            raise ApiError(400, "请输入 NS Internal ID")
        return self.ns.request("GET", record_type, record_id)

    def query(self, body):
        return self.records(body["type"], body["id"] if body["mode"] == "detail" else None)
