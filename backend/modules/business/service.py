"""旧来源存储用例装配（第 4e 步随 business 模块删除）；采购报关联查已移至 source。"""

from .storage_service import StorageService


class BusinessService:
    def __init__(self, ns, database_engine=None):
        self.ns = ns
        self.database_engine = database_engine
        self.storage = StorageService(ns, database_engine)
