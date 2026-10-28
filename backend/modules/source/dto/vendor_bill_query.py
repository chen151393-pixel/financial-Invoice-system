"""按 NS 供应商与母采购内部 ID 批量查询账单。"""

from typing import Annotated

from pydantic import Field, field_validator

from backend.core.dto import StrictModel

NsId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]


class VendorBillQuery(StrictModel):
    vendorId: NsId
    purchaseOrderIds: list[NsId] = Field(min_length=1, max_length=20)

    @field_validator("purchaseOrderIds")
    @classmethod
    def unique_orders(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("母采购内部 ID 不能重复")
        return value
