"""记录查询请求；空目标等输入问题由后端处理。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel


class RecordQuery(StrictModel):
    type: str = Field(max_length=100)
    id: str = Field(default="", max_length=140)
    mode: Literal["list", "detail"]
