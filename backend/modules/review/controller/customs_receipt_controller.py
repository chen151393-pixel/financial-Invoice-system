"""海关回执接口：导入、列表与重新匹配。比对规则与可操作判断在后端。"""

from fastapi import APIRouter, Query

from backend.core.dependencies import Owner

from ..dto.customs_receipt_dto import (
    CustomsApproveRequest,
    CustomsImportRequest,
    CustomsReceiptQuery,
    CustomsRematchRequest,
)
from ..vo.customs_import_vo import CustomsImportJob, CustomsImportJobs
from ..vo.customs_receipt_vo import (
    CustomsApproveResult,
    CustomsImportHistory,
    CustomsReceiptList,
    RematchResult,
)


def create_router(service, approval, imports=None):
    router = APIRouter(prefix="/api/review/customs-receipts", tags=["海关报关单比对"])

    @router.get("/import-history", response_model=CustomsImportHistory)
    def import_history(
        owner: Owner,
        page: int = Query(1, ge=1),
        pageSize: int = Query(5, ge=1, le=20),
    ):
        return service.import_history(page, pageSize)

    @router.post("/approve-batch", response_model=CustomsApproveResult)
    def approve_batch(body: CustomsApproveRequest, owner: Owner):
        return approval.approve_batch(body, owner)

    @router.post("/import", response_model=CustomsImportJob, status_code=202)
    def import_file(body: CustomsImportRequest, owner: Owner):
        return imports.enqueue(body, owner)

    @router.get("/imports", response_model=CustomsImportJobs)
    def import_jobs(owner: Owner):
        return imports.browse(owner)

    @router.post("/query", response_model=CustomsReceiptList)
    def query(body: CustomsReceiptQuery, owner: Owner):
        return service.browse(body)

    @router.post("/rematch", response_model=RematchResult)
    def rematch(body: CustomsRematchRequest, owner: Owner):
        return service.rematch(body, owner)

    return router
