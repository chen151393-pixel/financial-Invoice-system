"""外部群通知仅保存本地草稿、人工发送记录，不接受客户端业务状态。"""

from datetime import datetime

from pydantic import Field, field_validator

from backend.core.dto import StrictModel


class NotificationDraft(StrictModel):
    revision: int = Field(ge=0)
    groupName: str = Field(max_length=200)
    employee: str = Field(max_length=100)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("groupName", "employee", "message")
    @classmethod
    def strip_text(cls, value):
        return value.strip()


class NotificationRecord(StrictModel):
    revision: int = Field(ge=1)
    sentAt: datetime
    note: str = Field(min_length=1, max_length=500)
    confirmed: bool

    @field_validator("sentAt", mode="before")
    @classmethod
    def parse_sent_at(cls, value):
        # 严格模型不会将HTTP JSON字符串隐式转成日期，只接受明确的ISO格式。
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
