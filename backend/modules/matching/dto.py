"""确认只接受来源行、分配数量和服务端快照标识，不信任前端金额。"""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoiceIds: list[Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]] = Field(
        min_length=1, max_length=100
    )


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: UUID
    snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    invoiceLineId: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    purchaseLineId: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    quantity: str = Field(pattern=r"^[0-9]{1,18}(\.[0-9]{1,8})?$")
    customsNo: str | None = Field(
        default=None, max_length=50, pattern=r"^(?:[Cc][Dd][A-Za-z0-9]+|[0-9]{18})$"
    )


class LinkPair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoiceLineId: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    purchaseLineId: str = Field(pattern=r"^[1-9][0-9]{0,19}$")


class LinkSelection(BaseModel):
    """整票关联只选择来源明细，不由调用方提供分配数量或金额。"""

    model_config = ConfigDict(extra="forbid")
    snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    pairs: list[LinkPair] = Field(min_length=1, max_length=100)
    customsNo: str | None = Field(
        default=None, max_length=50, pattern=r"^(?:[Cc][Dd][A-Za-z0-9]+|[0-9]{18})$"
    )


class LinkRequest(LinkSelection):
    requestId: UUID
    manualConfirmation: bool = Field(default=False, strict=True)
    manualReason: str = Field(default="", max_length=1000)
