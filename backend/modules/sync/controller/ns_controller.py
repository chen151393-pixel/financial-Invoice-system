"""连接状态与认证验证接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto import PullRequest, SourceKind


def create_router(service, pull_service):
    router = APIRouter(tags=["连接状态"])

    @router.get("/api/ns/status")
    def status(owner: Owner):
        return service.status()

    @router.post("/api/ns/connect")
    def connect(owner: Owner):
        return service.connect()

    @router.get("/api/ns/sync/sources")
    def sources(owner: Owner):
        return pull_service.sources()

    @router.post("/api/ns/sync/{kind}/pull")
    def pull(kind: SourceKind, body: PullRequest, owner: Owner):
        return pull_service.pull(kind, body)

    @router.post("/api/ns/sync/{kind}/pull-save")
    def pull_save(kind: SourceKind, body: PullRequest, owner: Owner):
        return pull_service.pull_and_save(kind, body, owner)

    @router.post("/api/sync/ns/progress")
    def create_progress(owner: Owner):
        return pull_service.progress.create(owner)

    @router.get("/api/sync/ns/progress/{identity}")
    def get_progress(identity: str, owner: Owner):
        return pull_service.progress.get(identity, owner)

    return router
