"""旧Auth调用方式的兼容适配；新入口直接使用IdentityService。"""

from .modules.identity.service import IdentityService


class Auth(IdentityService):
    def login(self, request, username, password):
        return super().login(
            username,
            password,
            origin=request.headers.get("origin"),
            ip=request.client.host if request.client else "unknown",
            session_token=request.cookies.get("ns_session"),
        )

    def owner(self, request):
        return super().owner(
            authorization=request.headers.get("authorization", ""),
            session_token=request.cookies.get("ns_session"),
            method=request.method,
            origin=request.headers.get("origin"),
        )

    def logout(self, request):
        super().logout(request.cookies.get("ns_session"))
