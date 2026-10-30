"""后台同步输入：范围、日期及每日计划均由后端严格校验。"""

import re
from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from backend.core.dto import StrictModel
from backend.modules.invoice.public import lemon_import_defaults

from .lemon_invoice_dto import PullLemonInvoices
from .schedule_dto import DailySchedule


class AccountScope(StrictModel):
    accountMode: Literal["all", "selected"] = "all"
    accountIds: list[str] = Field(default_factory=list, max_length=1000)
    excludedIds: list[str] = Field(default_factory=list, max_length=1000)
    businessTypes: list[str] = Field(default_factory=lemon_import_defaults, min_length=1, max_length=50)

    @field_validator("businessTypes")
    @classmethod
    def types(cls, value):
        return PullLemonInvoices.business_types(value)

    @field_validator("accountIds", "excludedIds")
    @classmethod
    def identifiers(cls, values):
        if len(set(values)) != len(values) or any(not re.fullmatch(r"[1-9][0-9]{0,19}", v) for v in values):
            raise PydanticCustomError("lemon_accounts", "账套编号格式错误或重复")
        return sorted(values)

    @model_validator(mode="after")
    def scope(self):
        if self.accountMode == "selected" and (not self.accountIds or self.excludedIds):
            raise PydanticCustomError("lemon_accounts", "指定账套模式须选择账套且不能设置排除项")
        if self.accountMode == "all" and self.accountIds:
            raise PydanticCustomError("lemon_accounts", "全部账套模式请通过排除项限定范围")
        return self


class SubmitBatch(AccountScope):
    requestId: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
    startDate: str
    endDate: str

    @model_validator(mode="after")
    def dates(self):
        try:
            start, end = date.fromisoformat(self.startDate), date.fromisoformat(self.endDate)
            valid = start <= end and 1900 <= start.year <= end.year <= 2100
            valid = valid and start.isoformat() == self.startDate and end.isoformat() == self.endDate
        except ValueError:
            valid = False
        if not valid:
            raise PydanticCustomError("lemon_dates", "请按先后顺序填写 1900—2100 年的有效开票日期")
        return self


class SavePlan(AccountScope, DailySchedule):
    """柠檬云计划：账套范围与业务类型，加公共的每日时间与回扫天数。"""


class RetryBatch(StrictModel):
    requestId: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
