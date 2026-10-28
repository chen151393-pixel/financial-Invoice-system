"""权限管理接口：飞书同步、同步范围、部门默认角色、个人角色；仅系统管理员。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.access_dto import RolesSave, ScopeSave, UserRolesSave
from ..vo.access_vo import AccessOverview, SyncRun


def create_router(access, sync, identity):
    router = APIRouter(prefix="/api/identity", tags=["人员与权限"])

    @router.get("/access", response_model=AccessOverview)
    def overview(owner: Owner):
        return access.overview(owner)

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

    return router
