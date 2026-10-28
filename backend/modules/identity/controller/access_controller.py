"""权限管理接口：飞书同步、同步范围、部门默认角色、个人角色；仅系统管理员。"""

from fastapi import APIRouter, Query

from backend.core.dependencies import Owner

from ..dto.access_dto import RolesSave, ScopeSave, UserRolesSave
from ..dto.directory_dto import DirectoryMemberQuery, DirectorySelection, UserAccessSave
from ..vo.access_vo import AccessOverview, SyncRun, UserList
from ..vo.directory_vo import DirectoryMembers, DirectoryPlan, DirectoryPreview, DirectoryResult


def create_router(access, sync, identity, previews):
    router = APIRouter(prefix="/api/identity", tags=["人员与权限"])

    @router.get("/access", response_model=AccessOverview)
    def overview(owner: Owner):
        return access.overview(owner)

    @router.get("/users", response_model=UserList)
    def list_users(
        owner: Owner,
        query: str = Query(default="", max_length=100),
        department_id: int | None = None,
        page: int = Query(default=1, ge=1),
    ):
        return access.list_users(owner, query, department_id, page)

    @router.post("/sync", response_model=SyncRun | None)
    def run_sync(owner: Owner):
        identity.require_manage(owner)
        sync.sync("manual", owner)
        return access.last_sync()

    @router.put("/scopes")
    def save_scopes(body: ScopeSave, owner: Owner):
        access.set_scopes(body.departmentIds, owner)
        return {"saved": True}

    @router.put("/departments/{department_id}/roles")
    def save_department_roles(department_id: int, body: RolesSave, owner: Owner):
        access.set_department_roles(department_id, body.roles, owner)
        return {"saved": True}

    @router.put("/users/{user_id}/roles")
    def save_user_roles(user_id: int, body: UserRolesSave, owner: Owner):
        access.set_user_roles(user_id, body.roles, body.customRoles, owner)
        return {"saved": True}

    @router.post("/directory/previews", response_model=DirectoryPreview)
    def preview_directory(owner: Owner):
        return previews.create(owner)

    @router.post("/directory/previews/{preview_id}/members", response_model=DirectoryMembers)
    def preview_members(preview_id: str, body: DirectoryMemberQuery, owner: Owner):
        return previews.members(preview_id, body.model_dump(), owner)

    @router.post("/directory/previews/{preview_id}/plan", response_model=DirectoryPlan)
    def preview_plan(preview_id: str, body: DirectorySelection, owner: Owner):
        return previews.plan(preview_id, body.model_dump(), owner)

    @router.post("/directory/previews/{preview_id}/sync", response_model=DirectoryResult)
    def confirm_directory(preview_id: str, body: DirectorySelection, owner: Owner):
        return previews.apply(preview_id, body.model_dump(), owner)

    @router.put("/users/{user_id}/access")
    def save_user_access(user_id: int, body: UserAccessSave, owner: Owner):
        access.set_user_access(user_id, body.roles, body.customRoles, body.enabled, owner)
        return {"saved": True}

    return router
