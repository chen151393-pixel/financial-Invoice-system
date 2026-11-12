"""页面权限配置及成员草稿预览。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.role_page_dto import RolePagesSave
from ..dto.role_page_dto import UserAccessPreview as PreviewRequest
from ..vo.role_page_vo import RolePageOverview, RolePages, UserAccessDetail, UserAccessPreview


def create_router(service, previews):
    router = APIRouter(prefix="/api/identity", tags=["角色页面权限"])

    @router.get("/role-pages", response_model=RolePageOverview)
    def overview(owner: Owner):
        return service.overview(owner)

    @router.put("/role-pages/{role}", response_model=RolePages)
    def save(role: str, body: RolePagesSave, owner: Owner):
        return service.save(role, body.pages, body.revision, owner)

    @router.post("/users/{user_id}/access-preview", response_model=UserAccessPreview)
    def preview(user_id: int, body: PreviewRequest, owner: Owner):
        return previews.preview(user_id, body.roles, body.customRoles, owner)

    @router.get("/users/{user_id}/access", response_model=UserAccessDetail)
    def user_detail(user_id: int, owner: Owner):
        return previews.detail(user_id, owner)

    return router
