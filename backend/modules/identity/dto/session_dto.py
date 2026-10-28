"""登录请求校验。"""

from pydantic import Field

from backend.core.dto import StrictModel


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=190)
    password: str = Field(min_length=1, max_length=1000)


class FeishuStart(StrictModel):
    # 登录前所在的站内页面；后端只接受站内相对路径，其余回到工作台
    returnTo: str = Field(default="/workbench", max_length=500)
