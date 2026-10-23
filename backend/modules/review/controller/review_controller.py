"""财务核对接口：报关单列表、整单审核与批量审核。身份与审核条件由后端验证。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.review_dto import ApproveRequest, BatchApproveRequest, DeclarationListQuery
from ..vo.review_vo import BatchApproveResult, Declaration, ReviewList


def create_router(service):
    router = APIRouter(prefix="/api/review", tags=["财务核对"])

    @router.post("/declarations/query", response_model=ReviewList)
    def declarations(body: DeclarationListQuery, owner: Owner):
        return service.browse(body)

    # 固定路径登记在 {declaration_id} 路由之前
    @router.post("/declarations/approve-batch", response_model=BatchApproveResult)
    def approve_batch(body: BatchApproveRequest, owner: Owner):
        return service.approve_batch(body, owner)

    @router.post("/declarations/{declaration_id}/approve", response_model=Declaration)
    def approve(declaration_id: int, body: ApproveRequest, owner: Owner):
        return service.approve(declaration_id, body, owner)

    return router
