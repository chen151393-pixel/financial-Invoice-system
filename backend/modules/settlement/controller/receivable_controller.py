"""报关应收汇只读接口，沿用结汇对账页面权限。"""

from fastapi import APIRouter, Path

from backend.core.dependencies import Owner

from ..dto.progress_dto import ProgressQuery
from ..dto.receivable_dto import ReceivableQuery
from ..vo.progress_vo import SettlementProgress
from ..vo.receivable_vo import ReceivableList


def create_router(receivables, details=None):
    router = APIRouter(prefix="/api/settlement/receivables", tags=["结汇报关应收汇"])

    @router.post("/query", response_model=ReceivableList)
    def query(body: ReceivableQuery, owner: Owner):
        return receivables.query(body)

    @router.post("/progress", response_model=SettlementProgress)
    def progress(body: ProgressQuery, owner: Owner):
        return receivables.progress(body)

    if details:
        from ..vo.declaration_detail_vo import DeclarationDetail
        from .document_controller import download

        @router.get("/{number}", response_model=DeclarationDetail)
        def declaration_detail(owner: Owner, number: str = Path(min_length=1, max_length=150)):
            return details.get(number)

        @router.get("/{number}/originals/{index}")
        def original_file(
            owner: Owner, number: str = Path(min_length=1, max_length=150), index: int = Path(ge=0)
        ):
            filename, content = details.original(number, index)
            media = "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream"
            return download(filename, content, media, inline=media == "application/pdf")

    return router
