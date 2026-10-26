"""开票任务列表查询。"""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.core.dto import StrictModel


class TaskListQuery(StrictModel):
    keyword: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9_-]*$")
    supplierId: str = Field(default="", max_length=20, pattern=r"^([1-9][0-9]*)?$")
    groupBy: Literal["supplier", "declaration"] = "supplier"
    status: Literal["current", "superseded", "all"] = "current"
    # 业务状态按报关单汇总（报关单下当前任务中最慢的阶段）；空为不限
    stage: Literal["", "notify", "invoicing", "documents", "completed"] = ""
    # 报关单创建日期（NS 创建时间的中国日期），须成对填写
    createdFrom: date | None = Field(default=None, strict=False)
    createdTo: date | None = Field(default=None, strict=False)
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def valid_dates(self):
        if bool(self.createdFrom) != bool(self.createdTo):
            raise ValueError("请同时填写报关单创建开始日期与结束日期")
        if self.createdFrom and self.createdFrom > self.createdTo:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class TaskBoardQuery(StrictModel):
    """采购开票任务台：只看未被替代的任务；node 为空表示全部进行中的任务。

    上线后只同步 NS 正式环境，任务台不提供 NS 环境筛选。
    """

    keyword: str = Field(default="", max_length=120)
    supplierId: str = Field(default="", max_length=20, pattern=r"^([1-9][0-9]*)?$")
    node: Literal["", "documents", "notification", "invoices", "comparison", "completion", "done"] = ""
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)


class ClosureRequest(StrictModel):
    requestId: UUID = Field(strict=False)
    purchaseBasisId: str = Field(pattern=r"^[1-9][0-9]*$")
    ledgerSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("差异结束说明不能为空")
        return value.strip()
