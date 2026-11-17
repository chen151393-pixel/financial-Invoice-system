"""数据同步中心合并执行记录接口：NS 与柠檬云发票批次按执行时间倒序，仅系统管理员可用。"""

from typing import Literal

from fastapi import APIRouter, Query

from backend.core.dependencies import Owner


def create_router(history):
    router = APIRouter(prefix="/api/sync", tags=["同步执行记录"])

    @router.get("/batches")
    def list_batches(
        owner: Owner,
        page: int = Query(1, ge=1),
        pageSize: int = Query(20, ge=1, le=100),
        phase: Literal["queued", "discovering", "running", "completed", "partial", "failed", "unknown"]
        | None = None,
        source: Literal["ns", "lemon"] | None = None,
    ):
        return history.list(owner, page, pageSize, phase, source)

    return router
