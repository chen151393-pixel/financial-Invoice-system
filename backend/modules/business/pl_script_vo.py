"""NS共用查询服务的展示契约；只接收十进制字符串，不接收原始脚本内部对象。"""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.core.dto import StrictModel

from .dto import PlScriptQuery


class ScriptRow(StrictModel):
    id: str
    side: Literal["customs", "purchase"]
    cells: list[str] = Field(min_length=15, max_length=17)
    note: str = ""
    missingCells: list[int] = Field(default_factory=list)
    sourceKey: str = ""
    customsRowId: str | None = None
    currency: str = ""


class ScriptGroup(StrictModel):
    id: str
    title: str
    rows: list[ScriptRow] = Field(max_length=4000)
    customsCount: int = Field(ge=0)
    purchaseCount: int = Field(ge=0)
    warnings: list[str]
    declarationId: str = ""
    recordNumber: str = ""
    plNumbers: str = ""
    company: str = ""
    reviewIssues: list[str] = Field(default_factory=list)


class ScriptDeclaration(StrictModel):
    id: str
    recordNumber: str
    declarationNumber: str
    date: str
    created: str


class ScriptCounts(StrictModel):
    customs: int = Field(ge=0)
    purchase: int = Field(ge=0)
    declarations: int = Field(ge=0)
    groups: int = Field(ge=0)


class ScriptComparisonResult(StrictModel):
    contractVersion: Literal[1, 2, 3]
    complete: Literal[True]
    source: Literal["netsuite-script"]
    account: str
    requestId: str
    query: PlScriptQuery
    readStartedAt: str
    readCompletedAt: str
    elapsedMs: int = Field(ge=0)
    monthDateLabel: str
    counts: ScriptCounts
    declarations: list[ScriptDeclaration] = Field(max_length=200)
    groups: list[ScriptGroup] = Field(max_length=200)

    @field_validator("contractVersion", mode="before")
    @classmethod
    def validate_version_type(cls, value):
        # Literal按值比较；不能把布尔值或浮点数当作脚本版本号。
        if type(value) is not int:
            raise ValueError("脚本契约版本须为整数")
        return value

    @model_validator(mode="after")
    def validate_cell_count(self):
        expected = 15 if self.contractVersion == 1 else 17
        if any(len(row.cells) != expected for group in self.groups for row in group.rows):
            raise ValueError("展示列数与脚本契约版本不一致")
        return self
