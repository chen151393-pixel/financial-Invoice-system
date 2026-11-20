"""报关应收汇查询：客户汇总与报关单明细共用一组筛选条件。"""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.core.dto import StrictModel

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Stage = Literal["all", "unregistered", "collected", "remit", "unpaid", "partial", "settled", "issue", "alert"]


class ReceivableQuery(StrictModel):
    consignee: Text200 = ""
    declarationNo: Text200 = ""
    currency: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] = ""
    route: Literal["all", "hk_transit", "direct"] = "all"
    # 结汇阶段；alert 为需要关注（香港滞留超期）。阶段只筛选报关单明细，客户汇总与合计不受影响
    stage: Stage = "all"
    exportFrom: date | None = Field(default=None, strict=False)
    exportTo: date | None = Field(default=None, strict=False)

    @model_validator(mode="after")
    def valid_export_dates(self):
        if self.exportFrom and self.exportTo and self.exportFrom > self.exportTo:
            raise ValueError("出口日期开始不能晚于结束")
        return self
