"""供应商群配置接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.supplier_group_dto import (
    GroupQuery,
    GroupSave,
    SupplierGroupMatch,
    SupplierProfileQuery,
    WecomGroupQuery,
)
from ..vo.supplier_group_vo import GroupBinding, GroupList, SupplierList, SupplierProfileList, WecomGroupList


def create_router(service, profiles):
    router = APIRouter(prefix="/api/tasks/supplier-groups", tags=["供应商群配置"])

    @router.post("/profiles/query", response_model=SupplierProfileList)
    def profile_list(body: SupplierProfileQuery, owner: Owner):
        return profiles.browse(body, owner)

    @router.post("/query", response_model=GroupList)
    def browse(body: GroupQuery, owner: Owner):
        return service.browse(body, owner)

    @router.post("/suppliers/query", response_model=SupplierList)
    def suppliers(body: GroupQuery, owner: Owner):
        return service.supplier_options(body)

    @router.post("/wecom/query", response_model=WecomGroupList)
    def wecom_groups(body: WecomGroupQuery, owner: Owner):
        return service.search_wecom(body, owner)

    @router.post("/wecom/match", response_model=WecomGroupList)
    def match_groups(body: SupplierGroupMatch, owner: Owner):
        return service.match_wecom(body, owner)

    @router.post("/save", response_model=GroupBinding)
    def save(body: GroupSave, owner: Owner):
        return service.save(body, owner)

    return router
