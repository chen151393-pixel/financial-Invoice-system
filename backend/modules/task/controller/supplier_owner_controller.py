"""供应商人员关联接口；页面授权由统一身份依赖校验。"""

from fastapi import APIRouter, Path

from backend.core.dependencies import Owner

from ..dto.supplier_owner_dto import OwnerChange, OwnerQuery, OwnerSave
from ..vo.supplier_owner_vo import OwnerHistory, OwnerImpact, OwnerList, OwnerOptions, OwnerSaved


def create_router(service):
    router = APIRouter(prefix="/api/task/supplier-owners", tags=["供应商人员关联"])

    @router.get("/options", response_model=OwnerOptions)
    def options(owner: Owner):
        return service.options()

    @router.post("/query", response_model=OwnerList)
    def query(body: OwnerQuery, owner: Owner):
        return service.browse(body)

    @router.get("/{supplier_id}/{company_id}/history", response_model=OwnerHistory)
    def history(owner: Owner, supplier_id: int = Path(ge=1), company_id: int = Path(ge=1)):
        return service.history(supplier_id, company_id)

    @router.post("/preview", response_model=OwnerImpact)
    def preview(body: OwnerChange, owner: Owner):
        return service.preview(body, owner)

    @router.post("/save", response_model=OwnerSaved)
    def save(body: OwnerSave, owner: Owner):
        return service.save(body, owner)

    return router
