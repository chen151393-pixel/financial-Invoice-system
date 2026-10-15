"""发票比对接口：发票比对视图、待审核队列、列表摘要、候选、审核动作与重新生成建议。"""

from typing import Annotated

from fastapi import APIRouter, Path

from backend.core.dependencies import Owner

from ..dto.matching_dto import (
    BatchBody,
    CancelBody,
    CandidateQuery,
    ConfirmBody,
    GenerateBody,
    ManualBody,
    QueueQuery,
    RejectBody,
    SummaryBody,
)
from ..vo.matching_vo import BatchResult, Candidates, GenerateResult, InvoiceMatching, Queue, Summaries

Id = Annotated[int, Path(ge=1, le=2**63 - 1)]


def create_router(queries, allocations, proposals):
    router = APIRouter(prefix="/api/matching", tags=["发票比对"])

    @router.get("/invoices/{invoice_id}", response_model=InvoiceMatching)
    def invoice(invoice_id: Id, owner: Owner):
        return queries.invoice(invoice_id)

    @router.post("/queue", response_model=Queue)
    def queue(body: QueueQuery, owner: Owner):
        return queries.queue(body)

    @router.post("/summaries", response_model=Summaries)
    def summaries(body: SummaryBody, owner: Owner):
        return queries.summaries(body)

    @router.post("/candidates/query", response_model=Candidates)
    def candidates(body: CandidateQuery, owner: Owner):
        return queries.candidates(body)

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

    return router
