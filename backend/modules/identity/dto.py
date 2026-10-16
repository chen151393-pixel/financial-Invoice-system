"""登录请求校验。"""

from pydantic import Field

from backend.core.dto import StrictModel


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=190)
    password: str = Field(min_length=1, max_length=1000)
