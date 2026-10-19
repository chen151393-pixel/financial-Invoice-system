"""工作台查询与全量筛选导出；复用当前认证，不执行业务写入。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.workbench_dto import WorkbenchQuery
from ..vo.workbench_vo import Workbench, WorkbenchExport


def create_router(service):
    router = APIRouter(prefix="/api/matching/workbench", tags=["发票工作台"])

    @router.post("/query", response_model=Workbench)
    def query(body: WorkbenchQuery, owner: Owner):
        return service.read(body)

    @router.post("/export", response_model=WorkbenchExport)
    def export(body: WorkbenchQuery, owner: Owner):
        return service.read(body, export=True)

    return router
