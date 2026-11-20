"""香港独立回款登记接口；人工填写，提交经原批次事务校验。"""

from fastapi import APIRouter, Path

from backend.core.dependencies import Owner

from ..dto.hk_receipt_dto import HkRegistrationPreview, RegisterHkReceipt
from ..vo.batch_vo import BatchDetail
from ..vo.hk_receipt_vo import HkRegistrationCheck
from .document_controller import download

JSON_BODY_LIMITS = {
    r"/api/settlement/hk-workbench/register": 12 * 1024 * 1024,
}


def create_router(service):
    router = APIRouter(tags=["香港回款登记"])

    @router.post("/api/settlement/hk-workbench/receipt-preview", response_model=HkRegistrationCheck)
    def preview(body: HkRegistrationPreview, owner: Owner):
        return service.preview(body)

    @router.post("/api/settlement/hk-workbench/register", response_model=BatchDetail)
    def register(body: RegisterHkReceipt, owner: Owner):
        return service.register(body, owner)

    @router.get("/api/settlement/batches/{batch_id}/bank-slip/file")
    def slip_file(owner: Owner, batch_id: int = Path(ge=1)):
        filename, content = service.file(batch_id)
        return download(filename, content, "application/pdf", inline=True)

    return router
