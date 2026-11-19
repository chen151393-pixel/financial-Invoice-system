"""通知草稿与人工发送登记；不接受客户端提交的业务状态。"""

from datetime import date, datetime

from pydantic import Field, field_validator

from backend.core.dto import StrictModel


class NotificationDraft(StrictModel):
    revision: int = Field(ge=0, description="当前最新通知版本，没有时为 0")
    groupName: str = Field(max_length=200)
    employee: str = Field(max_length=100)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("groupName", "employee", "message")
    @classmethod
    def strip_text(cls, value):
        return value.strip()


class NotificationBatchRecord(StrictModel):
    """批量登记线下已通知：通知日期按北京时间解释，旧客户端未传日期时取登记当时。"""

    taskIds: list[str] = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=300)
    notifiedOn: date | None = Field(default=None, description="通知日期 YYYY-MM-DD（北京时间），默认今天")

    @field_validator("notifiedOn", mode="before")
    @classmethod
    def parse_notified_on(cls, value):
        if isinstance(value, str):
            if len(value) != 10:
                raise ValueError("通知日期须为 YYYY-MM-DD")
            parsed = date.fromisoformat(value)
            if value != parsed.isoformat():
                raise ValueError("通知日期须为 YYYY-MM-DD")
            return parsed
        return value

    @field_validator("taskIds")
    @classmethod
    def unique_ids(cls, value):
        if any(not item.isascii() or not item.isdigit() or item.startswith("0") for item in value):
            raise ValueError("任务编号格式不正确")
        if len(set(value)) != len(value):
            raise ValueError("同一个任务不能重复提交")
        return value

    @field_validator("note")
    @classmethod
    def strip_note(cls, value):
        return value.strip()


class NotificationRecord(StrictModel):
    revision: int = Field(ge=1, description="登记的通知版本")
    sentAt: datetime
    note: str = Field(min_length=1, max_length=500)
    confirmed: bool

    @field_validator("sentAt", mode="before")
    @classmethod
    def parse_sent_at(cls, value):
        # 严格模型不会将 HTTP JSON 字符串隐式转成日期，只接受明确的 ISO 格式。
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
