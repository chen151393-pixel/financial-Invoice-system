"""采购报关联查：按 CD / PL / 报关单号实时查询 NS 共用脚本，只读，不入库。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.pl_comparison import PlScriptQuery
from ..vo.pl_comparison import ScriptComparisonResult


def create_router(service):
    router = APIRouter(prefix="/api/source", tags=["来源数据"])

    @router.post("/pl-comparison", response_model=ScriptComparisonResult)
    def pl_comparison(body: PlScriptQuery, owner: Owner):
        return service.query(body)

    return router
