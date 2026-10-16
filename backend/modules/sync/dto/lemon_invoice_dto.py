"""柠檬云账套选择与日期范围。"""

from datetime import date

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from backend.core.dto import StrictModel


class SelectLemonAccount(StrictModel):
    asid: str = Field(pattern=r"^[1-9][0-9]{0,19}$")


class PullLemonInvoices(SelectLemonAccount):
    requestId: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
    startDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    endDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

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
