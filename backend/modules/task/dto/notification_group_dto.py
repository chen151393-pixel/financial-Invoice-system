"""按列表组登记；成员由后端展开，客户端只提交组锚点和所见范围版本。"""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator

from backend.core.dto import StrictModel

from .notification_dto import NotificationBatchRecord


class NotificationGroupSelection(StrictModel):
    id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    scopeRevision: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("id")
    @classmethod
    def bounded_id(cls, value):
        if int(value) > 2**63 - 1:
            raise ValueError("任务组编号超出范围")
        return value


class NotificationGroupBatchRecord(StrictModel):
    groupBy: Literal["supplier", "declaration"]
    # 对应列表每页至多 50 组；每组原任务数不受旧接口的 50 条限制。
    groups: list[NotificationGroupSelection] = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=300)
    notifiedOn: date | None = None

    @field_validator("groups")
    @classmethod
    def unique_groups(cls, value):
        if len({item.id for item in value}) != len(value):
            raise ValueError("同一个任务组不能重复提交")
        return value

    @field_validator("notifiedOn", mode="before")
    @classmethod
    def parse_notified_on(cls, value):
        return NotificationBatchRecord.parse_notified_on(value)

    @field_validator("note")
    @classmethod
    def strip_note(cls, value):
        return NotificationBatchRecord.strip_note(value)
