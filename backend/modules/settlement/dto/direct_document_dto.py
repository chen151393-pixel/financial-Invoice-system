"""直接收汇资料按报关单查询，不接收收款金额或批次状态。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel

from .batch_dto import Text200


class DirectDocumentQuery(StrictModel):
    keyword: Text200 = ""
    consignee: Text200 = ""
    status: Literal["all", "pending_bill", "pending_contract", "stale", "complete"] = "all"
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=100)
