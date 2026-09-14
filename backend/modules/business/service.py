"""NS业务记录只读用例；后续标准化与持久化在本模块扩展。"""

from backend.core.errors import ApiError


class BusinessService:
    def __init__(self, ns):
        self.ns = ns

    def records(self, record_type, record_id=None):
        if record_id == "":
            raise ApiError(400, "请输入 NS Internal ID")
        return self.ns.request("GET", record_type, record_id)

    def query(self, body):
        return self.records(body["type"], body["id"] if body["mode"] == "detail" else None)
