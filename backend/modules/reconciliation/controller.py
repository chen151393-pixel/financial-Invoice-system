"""财务核对HTTP入口，身份与审核条件由后端验证。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from .dto import ApproveRequest, DeclarationListQuery, ReviewQuery
from .vo import Declaration, ReviewResult


def create_router(service):
    router = APIRouter(prefix="/api/reconciliation", tags=["财务核对"])

    @router.post("/declarations", response_model=ReviewResult)
    def declarations(body: DeclarationListQuery, owner: Owner):
        return service.browse(body, owner)

    @router.post("/query", response_model=ReviewResult)
    def query(body: ReviewQuery, owner: Owner):
        return service.query(body, owner)

    @router.post("/approve", response_model=Declaration)
    def approve(body: ApproveRequest, owner: Owner):
        return service.approve(body, owner)

    return router
