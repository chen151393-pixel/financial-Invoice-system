"""财务核对接口：报关单列表与整单审核。身份与审核条件由后端验证。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.review_dto import ApproveRequest, DeclarationListQuery
from ..vo.review_vo import Declaration, ReviewList


def create_router(service):
    router = APIRouter(prefix="/api/review", tags=["财务核对"])

    @router.post("/declarations/query", response_model=ReviewList)
    def declarations(body: DeclarationListQuery, owner: Owner):
        return service.browse(body)

    @router.post("/declarations/{declaration_id}/approve", response_model=Declaration)
    def approve(declaration_id: int, body: ApproveRequest, owner: Owner):
        return service.approve(declaration_id, body, owner)

    return router
