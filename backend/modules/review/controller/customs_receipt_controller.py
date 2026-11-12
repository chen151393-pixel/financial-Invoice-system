"""海关回执接口：导入、列表与重新匹配。比对规则与可操作判断在后端。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.customs_receipt_dto import CustomsImportRequest, CustomsReceiptQuery, CustomsRematchRequest
from ..vo.customs_receipt_vo import CustomsImportResult, CustomsReceiptList, RematchResult


def create_router(service):
    router = APIRouter(prefix="/api/review/customs-receipts", tags=["海关报关单比对"])

    @router.post("/import", response_model=CustomsImportResult)
    def import_file(body: CustomsImportRequest, owner: Owner):
        return service.import_file(body, owner)

    @router.post("/query", response_model=CustomsReceiptList)
    def query(body: CustomsReceiptQuery, owner: Owner):
        return service.browse(body)

    @router.post("/rematch", response_model=RematchResult)
    def rematch(body: CustomsRematchRequest, owner: Owner):
        return service.rematch(body, owner)

    return router
