"""每日定时计划的公共字段：版本、启用状态、每日执行时间与回扫天数（柠檬云与 NS 计划共用）。"""

import re

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from backend.core.dto import StrictModel


class DailySchedule(StrictModel):
    revision: int = Field(ge=0)
    enabled: bool
    times: list[str] = Field(min_length=1, max_length=8)
    lookbackDays: int = Field(ge=1, le=366)

    @field_validator("times")
    @classmethod
    def daily_times(cls, values):
        if len(set(values)) != len(values) or any(
            not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", v) for v in values
        ):
            raise PydanticCustomError("sync_times", "执行时间须为不重复的 HH:mm，每日最多 8 次")
        return sorted(values)
