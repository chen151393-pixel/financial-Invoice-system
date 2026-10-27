"""回签上传队列：清单先入库，文件分片接收，查询持久结果。"""

from uuid import UUID

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.signed_upload_dto import CreateSignedUpload, RetrySignedUpload, SignedUploadChunk
from ..vo.signed_upload_vo import SignedUploadBatch, SignedUploadBatches

# 仅放开分片传输和旧兼容入口；其他业务请求继续使用原 128 KB 边界。
JSON_BODY_LIMITS = {
    r"/api/tasks/signed-contracts/upload-jobs/[0-9a-f-]{36}/files/[0-9a-f-]{36}/chunks": 6 * 1024 * 1024,
    r"/api/tasks/signed-contracts/upload": 280 * 1024 * 1024,
}


def create_router(service):
    router = APIRouter(prefix="/api/tasks/signed-contracts/upload-jobs", tags=["回签上传队列"])

    @router.post("", response_model=SignedUploadBatch, status_code=202)
    def create(body: CreateSignedUpload, owner: Owner):
        return service.create(body, owner)

    @router.get("", response_model=SignedUploadBatches)
    def recent(owner: Owner):
        return service.recent(owner)

    @router.get("/{batch_id}", response_model=SignedUploadBatch)
    def get(batch_id: UUID, owner: Owner):
        return service.get(str(batch_id), owner)

    @router.post("/{batch_id}/files/{file_id}/chunks", response_model=SignedUploadBatch, status_code=202)
    def chunk(batch_id: UUID, file_id: UUID, body: SignedUploadChunk, owner: Owner):
        return service.chunk(str(batch_id), str(file_id), body, owner)

    @router.post("/{batch_id}/files/{file_id}/retry", response_model=SignedUploadBatch, status_code=202)
    def retry(batch_id: UUID, file_id: UUID, body: RetrySignedUpload, owner: Owner):
        return service.retry(str(batch_id), str(file_id), body, owner)

    return router
