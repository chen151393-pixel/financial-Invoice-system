"""回签合同批量上传请求：只接收原文件（base64）与可选的人工指定单号；归属与格式由后端判定。"""

from typing import Annotated

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel


class SignedFile(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    # 10 MB 文件的 base64 长度上限
    content: str = Field(min_length=1, max_length=13_981_016)
    orderNo: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] = ""


class SignedContractUpload(StrictModel):
    files: list[SignedFile] = Field(min_length=1, max_length=20)
