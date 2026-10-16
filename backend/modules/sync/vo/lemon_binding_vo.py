"""已有账号绑定的响应契约；不包含凭据和授权码。"""

from typing import Literal

from backend.core.dto import StrictModel


class BindingAction(StrictModel):
    allowed: bool
    reason: str


class BindingStatus(StrictModel):
    phase: Literal[
        "unbound", "awaiting_authorization", "awaiting_confirmation", "binding", "unknown", "bound"
    ]
    message: str
    mobile: str
    confirmationMobile: str
    verifiedAt: str | None
    redirectUri: str
    begin: BindingAction
    confirm: BindingAction
    verify: BindingAction
    sync: BindingAction


class BindingStarted(StrictModel):
    authorizationUrl: str
