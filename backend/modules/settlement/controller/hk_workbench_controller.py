"""香港中转工作区只读接口，复用结汇对账权限。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.hk_workbench_dto import HkReceiptPreview, HkWorkbenchQuery
from ..vo.hk_workbench_vo import HkExport, HkReceiptCheck, HkWorkbench


def create_router(service):
    router = APIRouter(prefix="/api/settlement/hk-workbench", tags=["香港中转工作区"])

    @router.post("/query", response_model=HkWorkbench)
    def query(body: HkWorkbenchQuery, owner: Owner):
        return service.query(body)

    @router.post("/preview", response_model=HkReceiptCheck)
    def preview(body: HkReceiptPreview, owner: Owner):
        return service.preview(body)

    @router.post("/export", response_model=HkExport)
    def export(body: HkWorkbenchQuery, owner: Owner):
        return service.export(body)

    return router
