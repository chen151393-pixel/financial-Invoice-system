"""同步情况接口：近 14 天各来源每天的执行结果，只读。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..vo.sync_health_vo import SyncHealth


def create_router(service):
    router = APIRouter(prefix="/api/sync", tags=["同步情况"])

    @router.get("/health", response_model=SyncHealth)
    def health(owner: Owner):
        return service.health()

    return router
