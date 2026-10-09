"""连接状态与认证验证接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from .dto import PullRequest, SourceKind


def create_router(service, pull_service):
    router = APIRouter(prefix="/api/ns", tags=["连接状态"])

    @router.get("/status")
    def status(owner: Owner):
        return service.status()

    @router.post("/connect")
    def connect(owner: Owner):
        return service.connect()

    @router.get("/sync/sources")
    def sources(owner: Owner):
        return pull_service.sources()

    @router.post("/sync/{kind}/pull")
    def pull(kind: SourceKind, body: PullRequest, owner: Owner):
        return pull_service.pull(kind, body)

    @router.post("/sync/{kind}/pull-save")
    def pull_save(kind: SourceKind, body: PullRequest, owner: Owner):
        return pull_service.pull_and_save(kind, body, owner)

    return router
