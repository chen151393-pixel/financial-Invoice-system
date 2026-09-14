"""请求边界、安全响应头与统一错误处理。"""

import json
import logging

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .errors import ApiError

logger = logging.getLogger("ns_api")


class RequestGuard:
    def __init__(self, app, secure):
        self.app, self.secure = app, secure

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def secured(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"same-origin"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
                        ),
                    ]
                )
                if self.secure:
                    headers.append((b"strict-transport-security", b"max-age=31536000"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            receiver = receive
            if scope["path"].startswith("/api/") and scope["method"] in ("POST", "PUT", "PATCH"):
                headers = dict(scope["headers"])
                if headers.get(b"content-type", b"").split(b";")[0].strip().lower() != b"application/json":
                    raise ApiError(415, "请求必须使用 application/json")
                buffer = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    buffer.extend(message.get("body", b""))
                    if len(buffer) > 128 * 1024:
                        raise ApiError(413, "请求体过大")
                    if not message.get("more_body", False):
                        break
                try:

                    def reject_constant(_):
                        raise ValueError()

                    json.loads(buffer, parse_constant=reject_constant)
                except (ValueError, RecursionError):
                    raise ApiError(400, "JSON 格式错误") from None
                sent = False

                async def replay():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {"type": "http.request", "body": bytes(buffer), "more_body": False}
                    return await receive()

                receiver = replay
            await self.app(scope, receiver, secured)
        except Exception as error:
            if started:
                raise
            if isinstance(error, ApiError):
                status, message = error.status, error.message
            else:
                logger.error("request_failed type=%s", type(error).__name__)
                status, message = 500, "服务处理失败，请检查服务器配置"
            await JSONResponse({"error": message}, status_code=status)(scope, receive, secured)


def register_error_handlers(app):
    @app.exception_handler(ApiError)
    async def api_error(_request, error):
        return JSONResponse({"error": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _error):
        # 错误不回显密码、请求体和私有字段。
        return JSONResponse({"error": "请求字段缺失、类型错误或包含多余字段"}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(_request, error):
        return JSONResponse(
            {"error": "接口不存在" if error.status_code == 404 else "不支持的请求方式"},
            status_code=error.status_code,
        )
