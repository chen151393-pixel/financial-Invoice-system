"""按 NS 供应商与母采购内部 ID 批量查询账单。"""

from typing import Annotated

from pydantic import Field, field_validator

from backend.core.dto import StrictModel

NsId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]


class VendorBillQuery(StrictModel):
    vendorId: NsId
    purchaseOrderIds: list[NsId] = Field(min_length=1, max_length=20)
    invoiceNumber: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("invoiceNumber")
    @classmethod
    def exact_invoice_number(cls, value):
        if value is not None and (value != value.strip() or any(ord(char) < 32 for char in value)):
            raise ValueError("发票号码须为完整原始号码，不能有首尾空白或控制字符")
        return value

    @field_validator("purchaseOrderIds")
    @classmethod
    def unique_orders(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("母采购内部 ID 不能重复")
        return value
