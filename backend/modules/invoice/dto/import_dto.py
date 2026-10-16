"""Excel 导入请求：只接收原文件（base64）与预览凭证，不接收前端生成的发票对象。"""

from pydantic import Field

from backend.core.dto import StrictModel


class ImportBody(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5592408)
    previewToken: str | None = Field(default=None, max_length=180)
