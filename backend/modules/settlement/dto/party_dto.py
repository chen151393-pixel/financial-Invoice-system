"""合同抬头请求。"""

from typing import Annotated

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel

MAX_STAMP_BYTES = 2 * 1024 * 1024


def text(maximum, minimum=0):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=minimum, max_length=maximum)]


class SavePartyRequest(StrictModel):
    # 为空表示新增
    id: int | None = Field(default=None, ge=1)
    name: text(300, 1)
    nameCn: text(255) = ""
    nameEn: text(255, 1)
    addressCn: text(500) = ""
    addressEn: text(500, 1)
    phone: text(100) = ""


class UploadStampRequest(StrictModel):
    fileName: text(255, 1)
    content: str = Field(min_length=1, max_length=4 * ((MAX_STAMP_BYTES + 2) // 3))
