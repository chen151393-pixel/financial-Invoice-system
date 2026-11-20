"""资料组合并的候选、不可变预览与确认请求。"""

from datetime import date
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.core.dto import StrictModel

from .batch_dto import Number, Text200


class SingleDocumentGroupRequest(StrictModel):
    declarationNo: Number


class DocumentMergeQuery(StrictModel):
    sourceDeclarationNo: Number
    keyword: Text200 = ""
    exportFrom: date | None = Field(default=None, strict=False)
    exportTo: date | None = Field(default=None, strict=False)
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.exportFrom and self.exportTo and self.exportFrom > self.exportTo:
            raise ValueError("出口日期开始不能晚于结束")
        return self


class DocumentMergePreviewRequest(StrictModel):
    sourceDeclarationNo: Number
    declarationNos: list[Number] = Field(min_length=1, max_length=100)
    # None：仅一份本单提单时默认共用；0：合并后再上传或核对；正数：指定本单提单。
    sharedBillId: int | None = Field(default=None, ge=0)


class MergeDocumentGroupsRequest(DocumentMergePreviewRequest):
    requestId: str
    previewToken: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("requestId")
    @classmethod
    def valid_id(cls, value):
        return str(UUID(value))
