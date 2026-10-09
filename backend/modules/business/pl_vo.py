"""PL 联查响应契约；金额等业务值均以源字段的十进制文本返回。"""

from typing import Literal

from backend.core.dto import StrictModel


class PlConfiguration(StrictModel):
    ready: bool
    reason: str


class PlRow(StrictModel):
    source: Literal["采购", "报关"]
    id: str
    group: str
    values: dict[str, str]


class PlResult(StrictModel):
    pl: str
    rows: list[PlRow]
    total: int
    page: int
    hasNext: bool
    warnings: list[str]
    queriedAt: str
