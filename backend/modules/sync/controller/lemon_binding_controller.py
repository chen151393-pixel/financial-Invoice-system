"""绑定 API 与已登记的固定回调地址；不在回调请求中执行外部绑定。"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from backend.core.dependencies import Owner

from ..dto.lemon_binding_dto import BeginBinding, ConfirmBinding
from ..vo.lemon_binding_vo import BindingStarted, BindingStatus

COOKIE = "lemon_binding"
COOKIE_PATH = "/api/"


def create_router(service):
    router = APIRouter(tags=["柠檬云账号绑定"])

    @router.get("/api/sync/lemon/binding", response_model=BindingStatus)
    def status(request: Request, owner: Owner):
        return service.status(owner, request.cookies.get(COOKIE))

    @router.post("/api/sync/lemon/binding/start", response_model=BindingStarted)
    def start(body: BeginBinding, response: Response, owner: Owner):
        cookie, result = service.begin(owner, body.mobile)
        response.set_cookie(
            COOKIE, cookie, max_age=600, httponly=True, secure=True, samesite="lax", path=COOKIE_PATH
        )
        return result

    @router.get("/api/lemon/oauth/callback")
    def callback(request: Request):
        codes = request.query_params.getlist("code")
        accepted = len(codes) == 1 and service.callback(request.cookies.get(COOKIE), codes[0])
        result = "returned" if accepted else "invalid"
        response = RedirectResponse(f"/sync/lemon?binding={result}", status_code=303)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/api/sync/lemon/binding/confirm", response_model=BindingStatus)
    def confirm(body: ConfirmBinding, request: Request, response: Response, owner: Owner):
        result = service.confirm(owner, request.cookies.get(COOKIE), body.password.get_secret_value())
        response.delete_cookie(COOKIE, path=COOKIE_PATH, secure=True, httponly=True, samesite="lax")
        return result

    @router.post("/api/sync/lemon/binding/verify", response_model=BindingStatus)
    def verify(request: Request, owner: Owner):
        return service.verify(owner, request.cookies.get(COOKIE))

    return router
