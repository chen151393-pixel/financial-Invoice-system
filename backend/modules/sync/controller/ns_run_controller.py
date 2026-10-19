"""NS 来源按批后台保存接口：提交后立即返回，按请求编号查询实际结果。"""

from fastapi import APIRouter, Path

from backend.core.dependencies import Owner

from ..dto.ns_run_dto import UUID, NsRunRequest


def create_router(runs):
    router = APIRouter(tags=["NS 同步批次"])

    @router.post("/api/sync/ns/runs", status_code=202)
    def start(body: NsRunRequest, owner: Owner):
        return runs.start(owner, body)

    @router.get("/api/sync/ns/runs/{request_id}")
    def read(owner: Owner, request_id: str = Path(pattern=UUID)):
        return runs.read(owner, request_id)

    return router
