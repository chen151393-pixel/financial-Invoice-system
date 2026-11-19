"""收汇总览查询：累计口径，按币种和境外收货人筛选。"""

from typing import Annotated

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel


class OverviewQuery(StrictModel):
    consignee: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    currency: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] = ""
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)
