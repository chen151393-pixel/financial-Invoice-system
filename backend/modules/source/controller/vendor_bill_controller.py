"""账单查询仅使用现有登录/服务身份，不开放保存动作。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.vendor_bill_query import VendorBillQuery
from ..vo.vendor_bill_query import VendorBillResult


def create_router(service):
    router = APIRouter(prefix="/api/source/vendor-bills", tags=["来源数据"])

    @router.post("/query", response_model=VendorBillResult)
    def query(body: VendorBillQuery, owner: Owner):
        return service.query(body)

    return router
