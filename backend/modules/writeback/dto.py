"""旧写入协议保持兼容；文本编辑入口交给服务器解析JSON。"""

from typing import Any, Literal

from pydantic import Field, StrictBool

from backend.core.dto import StrictModel


class PreviewBody(StrictModel):
    operation: Literal["create", "update"]
    type: str = Field(max_length=100)
    id: str | None = Field(default=None, max_length=140)
    payload: dict[str, Any]


class PreviewTextBody(StrictModel):
    operation: Literal["create", "update"]
    type: str = Field(max_length=100)
    id: str | None = Field(default=None, max_length=140)
    payloadText: str = Field(max_length=128 * 1024)


class ExecuteBody(StrictModel):
    previewId: str = Field(pattern=r"^[a-f0-9-]{36}$")
    confirm: StrictBool
