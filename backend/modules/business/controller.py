"""NS 采购报关联查接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from .dto import PlScriptQuery
from .pl_script_vo import ScriptComparisonResult


def create_router(service):
    router = APIRouter(prefix="/api/ns", tags=["业务记录"])

    @router.post("/pl-script-comparison", response_model=ScriptComparisonResult)
    def pl_script_comparison(body: PlScriptQuery, owner: Owner):
        return service.pl_script.query(body)

    return router
