"""登录请求校验。"""

from pydantic import Field

from backend.core.dto import StrictModel


class Login(StrictModel):
    username: str = Field(max_length=190)
    password: str = Field(max_length=1000)
