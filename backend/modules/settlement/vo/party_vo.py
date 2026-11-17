"""合同抬头响应。"""

from backend.core.dto import StrictModel


class Party(StrictModel):
    id: int
    name: str
    nameCn: str
    nameEn: str
    addressCn: str
    addressEn: str
    phone: str
    hasStamp: bool
    stampUrl: str
    updatedBy: str
    updatedAt: str


class PartyList(StrictModel):
    items: list[Party]
