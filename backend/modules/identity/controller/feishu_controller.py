"""飞书网页授权登录：发起、回调、登录页读取失败原因。

回调地址须与飞书开放平台登记的重定向 URL 完全一致：APP_ORIGIN + /api/session/feishu/callback。
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from ..dto.session_dto import FeishuStart
from ..vo.session_vo import FeishuOutcome, FeishuStartResult
from .session_controller import set_session_cookie

FLOW_COOKIE = "ns_login_flow"
FLOW_PATH = "/api/session/feishu"


def create_router(service, settings):
    router = APIRouter(prefix=FLOW_PATH, tags=["身份"])

    @router.post("/start", response_model=FeishuStartResult)
    def start(request: Request, response: Response, body: FeishuStart):
        url, browser = service.start(body.returnTo, request.headers.get("origin"))
        # 飞书回跳是跨站顶层导航，SameSite=Strict 的 Cookie 不会随回调发送，流程 Cookie 只能用 Lax；
        # 它只用于把回调绑定到发起登录的浏览器，不能代替会话。
        response.set_cookie(
            FLOW_COOKIE,
            browser,
            max_age=600,
            httponly=True,
            secure=settings.origin.startswith("https://"),
            samesite="lax",
            path=FLOW_PATH,
        )
        return FeishuStartResult(url=url)

    @router.get("/callback")
    def callback(request: Request, code: str = "", state: str = "", error: str = ""):
        token, target = service.callback(
            code=code[:512], state=state[:256], error=error[:100], browser=request.cookies.get(FLOW_COOKIE)
        )
        response = RedirectResponse(target, status_code=303)
        if token:
            set_session_cookie(response, token, settings)
        return response

    @router.get("/outcome", response_model=FeishuOutcome)
    def outcome(request: Request):
        return service.outcome(request.cookies.get(FLOW_COOKIE))

    return router
