"""当前身份发票的只读试匹配接口。"""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from backend.core.dependencies import Owner

from .dto import ConfirmRequest, LinkRequest, LinkSelection, SummaryRequest


def create_router(service):
    router = APIRouter(prefix="/api/matching", tags=["自动匹配"])

    @router.post("/summaries")
    def summaries(body: SummaryRequest, owner: Owner):
        return service.summaries(body.invoiceIds, owner)

    @router.get("/invoices/{invoice_id}")
    def preview(
        invoice_id: Annotated[int, Path(gt=0, le=18446744073709551615)],
        owner: Owner,
        customs_no: Annotated[
            str | None,
            Query(alias="customsNo", max_length=50, pattern=r"^(?:[Cc][Dd][A-Za-z0-9]+|[0-9]{18})$"),
        ] = None,
        purchase_query: Annotated[
            str | None, Query(alias="purchaseQuery", min_length=1, max_length=100)
        ] = None,
        invoice_line_id: Annotated[
            str | None, Query(alias="invoiceLineId", pattern=r"^[1-9][0-9]{0,19}$")
        ] = None,
        page: Annotated[int, Query(ge=1)] = 1,
    ):
        return service.preview(
            invoice_id,
            owner,
            customs_no=customs_no,
            purchase_query=purchase_query,
            invoice_line_id=invoice_line_id,
            page=page,
        )

    @router.post("/invoices/{invoice_id}/links/review")
    def review_links(
        invoice_id: Annotated[int, Path(gt=0, le=18446744073709551615)], body: LinkSelection, owner: Owner
    ):
        return service.review_links(invoice_id, body, owner)

    @router.post("/invoices/{invoice_id}/confirm")
    def confirm(
        invoice_id: Annotated[int, Path(gt=0, le=18446744073709551615)], body: ConfirmRequest, owner: Owner
    ):
        return service.confirm(invoice_id, body, owner)

    @router.post("/invoices/{invoice_id}/links")
    def link(
        invoice_id: Annotated[int, Path(gt=0, le=18446744073709551615)], body: LinkRequest, owner: Owner
    ):
        return service.link(invoice_id, body, owner)

    return router
