"""批次清单与分片上传；业务大小错误逐文件返回。"""

from uuid import UUID

from pydantic import Field

from backend.core.dto import StrictModel

from ..policy.signed_upload_policy import CHUNK_BYTES, MAX_FILES


class UploadManifestFile(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0, le=2**53 - 1)
    orderNo: str = Field(default="", max_length=150)


class CreateSignedUpload(StrictModel):
    # JSON 没有 UUID 原生类型，此字段明确接受 UUID 字符串，其余字段保持严格校验。
    requestId: UUID = Field(strict=False)
    files: list[UploadManifestFile] = Field(min_length=1, max_length=MAX_FILES)


class SignedUploadChunk(StrictModel):
    offset: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=4 * ((CHUNK_BYTES + 2) // 3))


class RetrySignedUpload(StrictModel):
    orderNo: str = Field(default="", max_length=150)
