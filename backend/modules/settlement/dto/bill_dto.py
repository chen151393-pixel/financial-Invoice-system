"""提单请求：文件以 base64 传输，字段由人工确认；操作者来自认证身份。"""

from datetime import date
from typing import Annotated

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel

MAX_BILL_BYTES = 8 * 1024 * 1024
Port = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Number = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class UploadBillRequest(StrictModel):
    fileName: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content: str = Field(min_length=1, max_length=4 * ((MAX_BILL_BYTES + 2) // 3))
    # 为空表示该提单对应批次内全部报关单
    declarationNos: list[Number] = Field(default_factory=list, max_length=200)


class UpdateBillRequest(StrictModel):
    blNo: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    portOfLoading: Port = ""
    portOfDischarge: Port = ""
    onBoardDate: date | None = Field(default=None, strict=False)
    declarationNos: list[Number] = Field(min_length=1, max_length=200)
