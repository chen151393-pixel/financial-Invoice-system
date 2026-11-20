"""报关应收汇只读接口，沿用结汇对账页面权限。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.receivable_dto import ReceivableQuery
from ..vo.receivable_vo import ReceivableList


def create_router(receivables):
    router = APIRouter(prefix="/api/settlement/receivables", tags=["结汇报关应收汇"])

    @router.post("/query", response_model=ReceivableList)
    def query(body: ReceivableQuery, owner: Owner):
        return receivables.query(body)

    return router
