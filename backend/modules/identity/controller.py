"""登录与退出接口；HTTP元数据在此转换为服务参数。"""

from fastapi import APIRouter, Request, Response

from backend.core.dependencies import Owner

from .dto import Login


def create_router(service, settings):
    router = APIRouter(prefix="/api/session", tags=["身份"])

    def set_session_cookie(response, token):
        response.set_cookie(
            "ns_session",
            token,
            max_age=8 * 3600,
            httponly=True,
            secure=settings.origin.startswith("https://"),
            samesite="strict",
            path="/",
        )

    @router.post("/local")
    def local_session(request: Request, response: Response):
        token = service.open_local_session(
            origin=request.headers.get("origin"),
            host=request.headers.get("host", ""),
            ip=request.client.host if request.client else "unknown",
            session_token=request.cookies.get("ns_session"),
        )
        set_session_cookie(response, token)
        return {"authenticated": True}

    @router.post("")
    def login(request: Request, response: Response, body: Login):
        token = service.login(
            body.username,
            body.password,
            origin=request.headers.get("origin"),
            ip=request.client.host if request.client else "unknown",
            session_token=request.cookies.get("ns_session"),
        )
        set_session_cookie(response, token)
        return {"authenticated": True}

    @router.delete("")
    def logout(request: Request, response: Response, owner: Owner):
        service.logout(request.cookies.get("ns_session"))
        response.delete_cookie(
            "ns_session",
            path="/",
            httponly=True,
            secure=settings.origin.startswith("https://"),
            samesite="strict",
        )
        return {"authenticated": False}

    return router
