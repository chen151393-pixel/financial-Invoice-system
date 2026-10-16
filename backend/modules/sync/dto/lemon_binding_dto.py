"""已有账号绑定输入；拒绝前端指定应用、身份、回调和业务状态。"""

from pydantic import Field, SecretStr

from backend.core.dto import StrictModel


class BeginBinding(StrictModel):
    mobile: str = Field(pattern=r"^1[0-9]{10}$")


class ConfirmBinding(StrictModel):
    password: SecretStr = Field(min_length=1, max_length=1000)
