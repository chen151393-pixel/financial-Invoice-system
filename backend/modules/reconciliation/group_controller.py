"""供应商群配置 HTTP 接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from .group_dto import GroupQuery, GroupSave, WecomGroupQuery
from .group_vo import GroupBinding, GroupList, SupplierList, WecomGroupList


def create_router(service):
    router = APIRouter(prefix="/api/reconciliation/supplier-groups", tags=["供应商群配置"])

    @router.post("/query", response_model=GroupList)
    def browse(body: GroupQuery, owner: Owner):
        return service.browse(owner, body)

    @router.post("/suppliers/query", response_model=SupplierList)
    def suppliers(body: GroupQuery, owner: Owner):
        return service.supplier_options(owner, body)

    @router.post("/wecom/query", response_model=WecomGroupList)
    def wecom_groups(body: WecomGroupQuery, owner: Owner):
        return service.search_wecom(owner, body)

    @router.post("/save", response_model=GroupBinding)
    def save(body: GroupSave, owner: Owner):
        return service.save(owner, body)

    return router
