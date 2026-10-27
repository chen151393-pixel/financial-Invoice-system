"""发票文件接口：批量上传，按发票号码找到比对通过的子采购单并归档到所属报关单文件夹。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.invoice_file_dto import InvoiceFileUpload
from ..vo.invoice_file_vo import InvoiceFileResult


def create_router(service):
    router = APIRouter(prefix="/api/matching/invoice-files", tags=["发票文件"])

    @router.post("/upload", response_model=InvoiceFileResult)
    def upload(body: InvoiceFileUpload, owner: Owner):
        return service.upload(body, owner)

    return router
