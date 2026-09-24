"""Excel导入接口，复用认证身份；不接收前端生成的发票对象。"""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from backend.core.dependencies import Owner

from .dto import ImportBody, InvoiceQuery


def create_router(service):
    router = APIRouter(prefix="/api/invoices", tags=["发票"])

    @router.get("/import/configuration")
    def configuration(owner: Owner):
        return service.configuration()

    @router.post("/import/preview")
    def preview(body: ImportBody, owner: Owner):
        return service.process(body, owner)

    @router.post("/import/confirm")
    def confirm(body: ImportBody, owner: Owner):
        return service.process(body, owner, commit=True)

    @router.get("")
    def list_invoices(query: Annotated[InvoiceQuery, Query()], owner: Owner):
        return service.list_invoices(query, owner)

    @router.get("/{invoice_id}")
    def invoice_detail(invoice_id: Annotated[int, Path(gt=0, le=18446744073709551615)], owner: Owner):
        return service.invoice_detail(invoice_id, owner)

    return router
