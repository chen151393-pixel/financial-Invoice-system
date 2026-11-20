"""结汇进度查询：与总览共用收货人与币种筛选，不受客户明细分页影响。"""

from typing import Annotated

from pydantic import StringConstraints

from backend.core.dto import StrictModel


class ProgressQuery(StrictModel):
    consignee: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    currency: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] = ""
