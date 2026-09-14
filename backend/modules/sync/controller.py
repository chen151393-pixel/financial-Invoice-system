"""连接状态与认证验证接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner


def create_router(service):
    router = APIRouter(prefix="/api/ns", tags=["连接状态"])

    @router.get("/status")
    def status(owner: Owner):
        return service.status()

    @router.post("/connect")
    def connect(owner: Owner):
        return service.connect()

    return router
