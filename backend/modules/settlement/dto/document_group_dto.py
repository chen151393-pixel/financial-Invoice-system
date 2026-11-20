"""资料组创建只接收成员与幂等标识；客户、币种与金额均由后端读取。"""

from uuid import UUID

from pydantic import Field, field_validator

from backend.core.dto import StrictModel

from .batch_dto import Number
from .direct_document_dto import DirectDocumentQuery


class CreateDocumentGroup(StrictModel):
    requestId: str
    declarationNos: list[Number] = Field(min_length=1, max_length=100)

    @field_validator("requestId")
    @classmethod
    def valid_request(cls, value):
        return str(UUID(value))


DocumentGroupQuery = DirectDocumentQuery


class ConfirmGroupBasis(StrictModel):
    token: str = Field(pattern=r"^[0-9a-f]{64}$")
