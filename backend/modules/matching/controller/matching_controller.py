"""发票比对接口：发票比对视图、待审核队列、列表摘要、按匹配状态筛选的发票列表、候选、审核动作与重新生成建议。"""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from backend.core.dependencies import Owner

from ..dto.invoice_list_dto import InvoiceListQuery
from ..dto.invoice_totals_dto import InvoiceTotalsQuery
from ..dto.matching_dto import (
    BatchBody,
    CancelBody,
    CandidateQuery,
    ConfirmBody,
    GenerateBody,
    ManualBody,
    QueueQuery,
    RejectBody,
    ReplaceBody,
    SummaryBody,
)
from ..dto.order_matching_dto import OrderCandidateQuery, OrderConfirmBody
from ..vo.invoice_list_vo import InvoiceListResult
from ..vo.invoice_queue_vo import InvoiceQueue
from ..vo.invoice_totals_vo import InvoiceTotals
from ..vo.matching_vo import BatchResult, Candidates, GenerateResult, InvoiceMatching, Queue, Summaries
from ..vo.order_matching_vo import OrderCandidates

Id = Annotated[int, Path(ge=1, le=2**63 - 1)]


def create_router(queries, allocations, proposals, invoice_lists):
    router = APIRouter(prefix="/api/matching", tags=["发票比对"])

    @router.get("/invoice-totals", response_model=InvoiceTotals)
    def invoice_totals(query: Annotated[InvoiceTotalsQuery, Query()], owner: Owner):
        return queries.invoice_totals(query)

    @router.post("/invoices/query", response_model=InvoiceListResult)
    def invoice_list(body: InvoiceListQuery, owner: Owner):
        """进项发票列表按匹配状态筛选；返回与发票列表相同的分页结果、各状态张数和本页匹配摘要。"""
        return invoice_lists.query(body)

    @router.get("/invoices/{invoice_id}", response_model=InvoiceMatching)
    def invoice(invoice_id: Id, owner: Owner):
        return queries.invoice(invoice_id)

    @router.post("/queue", response_model=Queue)
    def queue(body: QueueQuery, owner: Owner):
        return queries.queue(body)

    @router.post("/invoice-queue/query", response_model=InvoiceQueue)
    def invoice_queue(body: QueueQuery, owner: Owner):
        return queries.invoice_queue(body)

    @router.post("/summaries", response_model=Summaries)
    def summaries(body: SummaryBody, owner: Owner):
        return queries.summaries(body)

    @router.post("/candidates/query", response_model=Candidates)
    def candidates(body: CandidateQuery, owner: Owner):
        return queries.candidates(body)

    @router.post("/order-candidates/query", response_model=OrderCandidates)
    def order_candidates(body: OrderCandidateQuery, owner: Owner):
        return queries.order_candidates(body)

    @router.post("/orders/confirm", response_model=InvoiceMatching)
    def confirm_order(body: OrderConfirmBody, owner: Owner):
        return allocations.confirm_order(body, owner)

    @router.post("/allocations/{allocation_id}/confirm", response_model=InvoiceMatching)
    def confirm(allocation_id: Id, body: ConfirmBody, owner: Owner):
        return allocations.confirm(allocation_id, body, owner)

    @router.post("/allocations/{allocation_id}/reject", response_model=InvoiceMatching)
    def reject(allocation_id: Id, body: RejectBody, owner: Owner):
        return allocations.reject(allocation_id, body, owner)

    @router.post("/allocations/{allocation_id}/cancel", response_model=InvoiceMatching)
    def cancel(allocation_id: Id, body: CancelBody, owner: Owner):
        return allocations.cancel(allocation_id, body, owner)

    @router.post("/allocations", response_model=InvoiceMatching)
    def create(body: ManualBody, owner: Owner):
        return allocations.create_manual(body, owner)

    @router.post("/allocations/confirm-batch", response_model=BatchResult)
    def confirm_batch(body: BatchBody, owner: Owner):
        return allocations.confirm_batch(body, owner)

    @router.post("/proposals/generate", response_model=GenerateResult)
    def generate(body: GenerateBody, owner: Owner):
        return {"created": proposals.generate_now([int(value) for value in body.invoiceIds], owner)}

    @router.post("/allocations/{allocation_id}/reverify", response_model=InvoiceMatching)
    def reverify(allocation_id: Id, body: ConfirmBody, owner: Owner):
        return allocations.reverify(allocation_id, body, owner)

    @router.post("/allocations/{allocation_id}/replace", response_model=InvoiceMatching)
    def replace(allocation_id: Id, body: ReplaceBody, owner: Owner):
        return allocations.replace(allocation_id, body, owner)

    return router
