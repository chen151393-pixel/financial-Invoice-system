"""回签合同接口：批量上传，按文件名识别子采购单并归档到所属报关单文件夹。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.signed_contract_dto import SignedContractUpload
from ..vo.signed_contract_vo import SignedUploadResult


def create_router(service):
    router = APIRouter(prefix="/api/tasks/signed-contracts", tags=["回签合同"])

    @router.post("/upload", response_model=SignedUploadResult)
    def upload(body: SignedContractUpload, owner: Owner):
        return service.upload(body, owner)

    return router
