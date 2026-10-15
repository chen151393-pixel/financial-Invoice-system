"""进项发票接口：Excel 导入（配置、预览、确认）与列表、详情。"""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from backend.core.dependencies import Owner

from ..dto.import_dto import ImportBody
from ..dto.invoice_dto import InvoiceQuery
from ..vo.import_vo import ImportConfiguration, ImportResult
from ..vo.invoice_vo import InvoiceDetail, InvoiceList


def create_router(imports, invoices):
    router = APIRouter(prefix="/api/invoices", tags=["发票"])

    @router.get("/import/configuration", response_model=ImportConfiguration)
    def configuration(owner: Owner):
        return imports.configuration()

    @router.post("/import/preview", response_model=ImportResult)
    def preview(body: ImportBody, owner: Owner):
        return imports.process(body, owner)

    @router.post("/import/confirm", response_model=ImportResult)
    def confirm(body: ImportBody, owner: Owner):
        return imports.process(body, owner, commit=True)

    @router.get("", response_model=InvoiceList)
    def browse(query: Annotated[InvoiceQuery, Query()], owner: Owner):
        return invoices.browse(query)

    @router.get("/{invoice_id}", response_model=InvoiceDetail)
    def detail(invoice_id: Annotated[int, Path(ge=1, le=2**63 - 1)], owner: Owner):
        return invoices.detail(invoice_id)

    return router
