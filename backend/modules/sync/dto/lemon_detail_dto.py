"""单张和批量补拉共用请求；账套、日期和来源编号全部由服务端读取。"""

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from backend.core.dto import StrictModel


class LemonDetailSelection(StrictModel):
    invoiceIds: list[Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]] = Field(
        min_length=1, max_length=100
    )

    @field_validator("invoiceIds")
    @classmethod
    def unique_ids(cls, values):
        if len(set(values)) != len(values):
            raise PydanticCustomError("duplicate_invoices", "不能重复选择发票")
        return sorted(values, key=int)


class RefreshLemonDetails(LemonDetailSelection):
    requestId: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
