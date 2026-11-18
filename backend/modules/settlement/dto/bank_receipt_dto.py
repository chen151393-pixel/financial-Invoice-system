"""银行收汇明细查询请求。"""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.core.dto import StrictModel

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
MAX_IMPORT_BYTES = 4 * 1024 * 1024


class BankReceiptImportRequest(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=((MAX_IMPORT_BYTES + 2) // 3) * 4)


class BankReceiptQuery(StrictModel):
    # 实际客户（境外收货人），包含匹配
    customer: Text200 = ""
    # 收汇抬头（我方收款主体），包含匹配
    receivingCompany: Text200 = ""
    receiptFrom: date | None = Field(default=None, strict=False)
    receiptTo: date | None = Field(default=None, strict=False)
    thirdParty: Literal["all", "yes", "no"] = "all"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.receiptFrom and self.receiptTo and self.receiptFrom > self.receiptTo:
            raise ValueError("收汇日期开始不能晚于结束")
        return self
