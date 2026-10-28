"""供应商群配置接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.supplier_group_dto import (
    GroupQuery,
    GroupSave,
    SupplierGroupMatch,
    SupplierNotifySave,
    SupplierProfileQuery,
    WecomGroupQuery,
)
from ..vo.supplier_group_vo import (
    GroupBinding,
    GroupList,
    InvoicingSpeed,
    SupplierList,
    SupplierNotify,
    SupplierProfileList,
    WecomGroupList,
)


def create_router(service, profiles):
    router = APIRouter(prefix="/api/tasks/supplier-groups", tags=["供应商群配置"])

    @router.post("/profiles/query", response_model=SupplierProfileList)
    def profile_list(body: SupplierProfileQuery, owner: Owner):
        return profiles.browse(body, owner)

    @router.get("/profiles/invoicing-speed", response_model=InvoicingSpeed)
    def invoicing_speed(owner: Owner):
        """近 90 天：通知供应商到发票收齐的平均天数，按供应商从慢到快。"""
        return profiles.invoicing_speed()

    @router.post("/profiles/notify", response_model=SupplierNotify)
    def profile_notify(body: SupplierNotifySave, owner: Owner):
        return profiles.set_notify(body, owner)

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

    combined = APIRouter()
    combined.add_api_route(
        "/api/task/supplier-groups/profiles/query",
        profile_list,
        methods=["POST"],
        response_model=SupplierProfileList,
        tags=["供应商群配置"],
    )
    # 兼容旧前端一个版本；当前前端已切换到 task 模块路径。
    combined.include_router(router)
    return combined
