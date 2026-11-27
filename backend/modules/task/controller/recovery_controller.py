"""应收看板接口：按财务审核通过月份审计发票回收，只读；页面授权为 invoice-recovery。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.recovery_dto import RecoveryQuery
from ..vo.recovery_vo import RecoveryBoard, RecoveryExport


def create_router(service):
    router = APIRouter(prefix="/api/task/recovery", tags=["应收看板"])

    @router.post("/query", response_model=RecoveryBoard)
    def query(body: RecoveryQuery, owner: Owner):
        return service.browse(body)

    @router.post("/export", response_model=RecoveryExport)
    def export(body: RecoveryQuery, owner: Owner):
        return service.export(body)

    return router
