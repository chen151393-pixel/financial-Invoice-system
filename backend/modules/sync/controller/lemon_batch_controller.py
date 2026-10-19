"""同步批次、任务详情与计划设置。"""

from typing import Literal

from fastapi import APIRouter, Query

from backend.core.dependencies import Owner

from ..dto.lemon_batch_dto import RetryBatch, SavePlan, SubmitBatch


def create_router(batches, plans):
    router = APIRouter(prefix="/api/sync/lemon", tags=["柠檬云后台同步"])

    @router.get("/background/configuration")
    def configuration(owner: Owner):
        return plans.configuration(owner)

    @router.put("/plan")
    def save_plan(body: SavePlan, owner: Owner):
        return plans.save(owner, body)

    @router.post("/batches", status_code=202)
    def submit(body: SubmitBatch, owner: Owner):
        return batches.submit(owner, body)

    @router.get("/batches")
    def list_batches(
        owner: Owner,
        page: int = Query(1, ge=1),
        pageSize: int = Query(20, ge=1, le=100),
        phase: Literal["queued", "discovering", "running", "completed", "partial", "failed", "unknown"]
        | None = None,
    ):
        return batches.list(owner, page, pageSize, phase)

    @router.get("/batches/{request_id}")
    def detail(request_id: str, owner: Owner, page: int = Query(1, ge=1)):
        return batches.read(owner, request_id, page)

    @router.post("/batches/{request_id}/retry", status_code=202)
    def retry(request_id: str, body: RetryBatch, owner: Owner):
        return batches.retry(owner, request_id, body)

    return router
