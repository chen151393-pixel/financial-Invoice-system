"""NS 定时计划输入：单据范围加公共的每日时间与回扫天数，均由后端校验。"""

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from ..policy.ns_plan_policy import KINDS
from .ns_run_dto import SaveKind
from .schedule_dto import DailySchedule


class SaveNsPlan(DailySchedule):
    kinds: list[SaveKind] = Field(min_length=1, max_length=len(KINDS))

    @field_validator("kinds")
    @classmethod
    def unique_kinds(cls, values):
        if len(set(values)) != len(values):
            raise PydanticCustomError("ns_plan_kinds", "同步单据类型不能重复")
        # 固定执行顺序：先报关单（带出关联子采购），再子采购单。
        return [kind for kind in KINDS if kind in values]
