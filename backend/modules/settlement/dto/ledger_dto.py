"""直接收汇明细（总账）查询请求。"""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class LedgerQuery(StrictModel):
    # 境外收货人，包含匹配
    consignee: Text200 = ""
    # 出口抬头或收汇抬头（我方主体），包含匹配
    company: Text200 = ""
    status: Literal["all", "outstanding", "settled", "overpaid"] = "all"
    # 按境外收货人分页：一页若干个收货人，每个收货人的流水完整返回
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)
