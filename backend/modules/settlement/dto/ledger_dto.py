"""直接收汇明细（总账）查询请求。"""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.core.dto import StrictModel

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class LedgerQuery(StrictModel):
    # 境外收货人，包含匹配
    consignee: Text200 = ""
    # 出口抬头或收汇抬头（我方主体），包含匹配
    company: Text200 = ""
    receivingCompany: Text200 = ""
    byRecipient: bool = False
    startDate: date | None = Field(default=None, strict=False)
    endDate: date | None = Field(default=None, strict=False)
    status: Literal["all", "outstanding", "settled", "overpaid"] = "all"
    # 按境外收货人分页：一页若干个收货人，每个收货人的流水完整返回
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def check_period(self):
        if bool(self.startDate) != bool(self.endDate):
            raise ValueError("请同时填写对账开始日期和结束日期")
        if self.startDate and self.endDate and self.startDate > self.endDate:
            raise ValueError("对账开始日期不能晚于结束日期")
        return self
