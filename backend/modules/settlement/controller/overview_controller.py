"""收汇总览只读接口，沿用结汇对账页面权限。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.overview_dto import OverviewQuery
from ..vo.overview_vo import OverviewList


def create_router(overview):
    router = APIRouter(prefix="/api/settlement/overview", tags=["结汇收汇总览"])

    @router.post("/query", response_model=OverviewList)
    def query(body: OverviewQuery, owner: Owner):
        return overview.query(body)

    return router
