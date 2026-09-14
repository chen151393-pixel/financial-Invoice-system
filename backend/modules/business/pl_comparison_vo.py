"""真实PL核对结果与同次读取的Excel文件；不返回任何认证凭证。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel


class ComparisonRow(StrictModel):
    id: str
    headId: str
    currency: str
    cells: list[str] = Field(min_length=15, max_length=15)


class ComparisonGroup(StrictModel):
    id: str
    pl: str
    company: str
    summary: str
    status: str
    customs: list[ComparisonRow]
    purchases: list[ComparisonRow]


class ComparisonDownload(StrictModel):
    filename: str
    contentBase64: str
    mediaType: Literal["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]


class ComparisonResult(StrictModel):
    pl: str
    company: str
    account: str
    queriedAt: str
    source: Literal["netsuite-rest"]
    groups: list[ComparisonGroup]
    warnings: list[str]
    download: ComparisonDownload | None
