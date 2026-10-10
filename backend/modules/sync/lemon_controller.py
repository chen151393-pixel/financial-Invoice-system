"""公开回调探测、管理员配置查询与授权发起接口。"""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from backend.core.dependencies import Owner
from backend.core.errors import ApiError

from .dto import LemonAuthorizationRequest, LemonCallbackRequest
from .lemon_service import AUTHORIZATION_TTL, CALLBACK_COOKIE, CALLBACK_PATH


def create_router(service, settings):
    router = APIRouter(prefix="/api/lemon/oauth", tags=["柠檬云授权回调"])

    @router.get("/configuration")
    def configuration(owner: Owner):
        return service.configuration()

    @router.post("/authorize")
    def authorize(body: LemonAuthorizationRequest, owner: Owner, request: Request, response: Response):
        result, token = service.begin(owner, request.cookies.get("ns_session"), body)
        # 柠檬云跨站 GET 返回时原 ns_session 的 Strict cookie 不会发送；
        # 使用单独 Lax cookie，不放宽现有管理员会话的安全属性。
        response.set_cookie(
            CALLBACK_COOKIE,
            token,
            max_age=AUTHORIZATION_TTL,
            httponly=True,
            secure=settings.origin.startswith("https://"),
            samesite="lax",
            path=CALLBACK_PATH,
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        return result

    @router.get("/callback")
    def callback(body: Annotated[LemonCallbackRequest, Query()], request: Request, response: Response):
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise ApiError(400, "回调参数不能重复")
        result = service.receive(body, request.cookies.get(CALLBACK_COOKIE))
        response.headers["Referrer-Policy"] = "no-referrer"
        if body.code is not None:
            response.delete_cookie(
                CALLBACK_COOKIE,
                path=CALLBACK_PATH,
                httponly=True,
                secure=settings.origin.startswith("https://"),
                samesite="lax",
            )
        return result

    return router
