"""NS 定时同步计划与计划批次接口：仅系统管理员可用，校验与执行均在后端。"""

from typing import Literal

from fastapi import APIRouter, Path, Query

from backend.core.dependencies import Owner

from ..dto.ns_plan_dto import SaveNsPlan
from ..dto.ns_run_dto import UUID


def create_router(plans, batches):
    router = APIRouter(prefix="/api/sync/ns", tags=["NS 定时同步计划"])

    @router.get("/plan")
    def configuration(owner: Owner):
        return plans.configuration(owner)

    @router.put("/plan")
    def save_plan(body: SaveNsPlan, owner: Owner):
        return plans.save(owner, body)

    @router.get("/batches")
    def list_batches(
        owner: Owner,
        page: int = Query(1, ge=1),
        pageSize: int = Query(20, ge=1, le=100),
        phase: Literal["queued", "running", "completed", "partial", "failed", "unknown"] | None = None,
    ):
        return batches.list(owner, page, pageSize, phase)

    @router.get("/batches/{request_id}")
    def detail(owner: Owner, request_id: str = Path(pattern=UUID)):
        return batches.read(owner, request_id)

    return router
