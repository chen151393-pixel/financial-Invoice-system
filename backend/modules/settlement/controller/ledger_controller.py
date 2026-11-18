"""直接收汇明细（总账）接口：总账差额、状态与合计在后端计算。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.ledger_dto import LedgerQuery
from ..vo.ledger_vo import LedgerList


def create_router(ledger):
    router = APIRouter(prefix="/api/settlement/ledger", tags=["结汇直接收汇明细"])

    @router.post("/query", response_model=LedgerList)
    def query(body: LedgerQuery, owner: Owner):
        return ledger.query(body)

    return router
