"""结汇接口：可结汇报关单、批次列表与详情、建批次及状态操作。金额核对与可操作判断在后端。"""

from fastapi import APIRouter, Path

from backend.core.dependencies import Owner

from ..dto.batch_dto import BatchQuery, CancelRequest, CandidateQuery, CreateBatchRequest, RemittanceRequest
from ..vo.batch_vo import BatchDetail, BatchList, CandidateList

BatchId = Path(ge=1)


def create_router(candidates, batches):
    router = APIRouter(prefix="/api/settlement", tags=["结汇"])

    @router.post("/candidates/query", response_model=CandidateList)
    def query_candidates(body: CandidateQuery, owner: Owner):
        return candidates.query(body)

    @router.post("/batches/query", response_model=BatchList)
    def query_batches(body: BatchQuery, owner: Owner):
        return batches.browse(body)

    @router.post("/batches", response_model=BatchDetail)
    def create_batch(body: CreateBatchRequest, owner: Owner):
        return batches.create(body, owner)

    @router.get("/batches/{batch_id}", response_model=BatchDetail)
    def get_batch(owner: Owner, batch_id: int = BatchId):
        return batches.get(batch_id)

    @router.post("/batches/{batch_id}/documents-ready", response_model=BatchDetail)
    def documents_ready(owner: Owner, batch_id: int = BatchId):
        return batches.documents_ready(batch_id, owner)

    @router.post("/batches/{batch_id}/remittance", response_model=BatchDetail)
    def remittance(body: RemittanceRequest, owner: Owner, batch_id: int = BatchId):
        return batches.remit(batch_id, body, owner)

    @router.post("/batches/{batch_id}/settle", response_model=BatchDetail)
    def settle(owner: Owner, batch_id: int = BatchId):
        return batches.settle(batch_id, owner)

    @router.post("/batches/{batch_id}/cancel", response_model=BatchDetail)
    def cancel(body: CancelRequest, owner: Owner, batch_id: int = BatchId):
        return batches.cancel(batch_id, body, owner)

    return router
