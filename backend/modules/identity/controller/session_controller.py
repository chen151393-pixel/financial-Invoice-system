"""登录与退出接口；HTTP元数据在此转换为服务参数。"""

from fastapi import APIRouter, Request, Response

from backend.core.dependencies import Owner

from ..dto.session_dto import Login
from ..vo.session_vo import LoginOptions, SessionInfo

SESSION_COOKIE = "ns_session"


def set_session_cookie(response, token, settings):
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=8 * 3600,
        httponly=True,
        secure=settings.origin.startswith("https://"),
        samesite="strict",
        path="/",
    )


def create_router(service, settings, feishu):
    router = APIRouter(prefix="/api/session", tags=["身份"])

    @router.get("", response_model=SessionInfo)
    def session(owner: Owner):
        return SessionInfo(authenticated=True, user=service.describe(owner))

    @router.get("/options", response_model=LoginOptions)
    def options():
        """登录页显示哪些登录方式；未登录也可读取，不含任何凭证。"""
        return LoginOptions(
            feishu=feishu.configured,
            password=settings.admin_password_login and bool(settings.admin_password),
        )

    @router.post("/local")
    def local_session(request: Request):
        return service.open_local_session(
            origin=request.headers.get("origin"),
            host=request.headers.get("host", ""),
            ip=request.client.host if request.client else "unknown",
            session_token=request.cookies.get(SESSION_COOKIE),
        )

    @router.post("")
    def login(request: Request, response: Response, body: Login):
        token = service.login(
            body.username,
            body.password,
            origin=request.headers.get("origin"),
            ip=request.client.host if request.client else "unknown",
            session_token=request.cookies.get(SESSION_COOKIE),
        )
        set_session_cookie(response, token, settings)
        return {"authenticated": True}

    @router.delete("")
    def logout(request: Request, response: Response, owner: Owner):
        service.logout(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            httponly=True,
            secure=settings.origin.startswith("https://"),
            samesite="strict",
        )
        return {"authenticated": False}

    return router
