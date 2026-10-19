"""柠檬云账套选择与日期范围。"""

from datetime import date

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from backend.core.dto import StrictModel
from backend.modules.invoice.public import lemon_import_defaults


class SelectLemonAccount(StrictModel):
    asid: str = Field(pattern=r"^[1-9][0-9]{0,19}$")


class PullLemonInvoices(SelectLemonAccount):
    requestId: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
    startDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    endDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    businessTypes: list[str] = Field(default_factory=lemon_import_defaults, min_length=1, max_length=50)

    @field_validator("businessTypes")
    @classmethod
    def business_types(cls, values):
        if any(not value.strip() or len(value) > 255 for value in values):
            raise PydanticCustomError("lemon_types", "业务类型不能为空，且每项最多 255 个字符")
        normalized = [value.strip() for value in values]
        if len(set(normalized)) != len(normalized):
            raise PydanticCustomError("lemon_types", "业务类型不能重复选择")
        return sorted(normalized)

    @model_validator(mode="after")
    def dates(self):
        try:
            start, end = date.fromisoformat(self.startDate), date.fromisoformat(self.endDate)
        except ValueError:
            raise PydanticCustomError("lemon_dates", "请填写有效的起止开票日期") from None
        if start > end or (end - start).days > 365 or not 1900 <= start.year <= end.year <= 2100:
            raise PydanticCustomError(
                "lemon_dates", "起止日期须按先后顺序填写，限 1900—2100 年且单次不超过 366 天"
            )
        return self
