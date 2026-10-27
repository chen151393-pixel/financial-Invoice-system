"""上传与后台处理的独立进度、逐文件状态。"""

from typing import Literal

from backend.core.dto import StrictModel


class SignedUploadJobFile(StrictModel):
    id: str
    filename: str
    size: int
    receivedBytes: int
    status: Literal["uploading", "queued", "running", "saved", "unmatched", "ambiguous", "conflict", "failed"]
    reason: str
    orderNumber: str
    archivePath: str | None
    canRetry: bool


class SignedUploadBatch(StrictModel):
    id: str
    phase: Literal["uploading", "queued", "running", "completed"]
    total: int
    finished: int
    saved: int
    progressPercent: int
    uploadPercent: int
    message: str
    chunkBytes: int
    maxFileBytes: int
    items: list[SignedUploadJobFile]


class SignedUploadBatches(StrictModel):
    items: list[SignedUploadBatch]
