"""请求边界、安全响应头与统一错误处理。"""

import json
import logging
import time

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
        started_at = time.monotonic()
        error_type = "HTTPResponse"

        async def secured(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                status = message["status"]
                if status >= 400:
                    # 使用路由模板，不记录路径参数、查询条件、正文或异常原文。
                    route = getattr(scope.get("route"), "path", "<unmatched>")
                    logger.log(
                        logging.ERROR if status >= 500 else logging.WARNING,
                        "request_failed method=%s route=%s status=%s type=%s duration_ms=%.1f",
                        scope["method"],
                        route,
                        status,
                        error_type,
                        (time.monotonic() - started_at) * 1000,
                    )
                elif scope["path"].startswith("/api/"):
                    logger.info(
                        "request_completed method=%s route=%s status=%s duration_ms=%.1f",
                        scope["method"],
                        getattr(scope.get("route"), "path", "<unmatched>"),
                        status,
                        (time.monotonic() - started_at) * 1000,
                    )
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
                # 仅两个原文件导入接口允许较大JSON，4MB文件经base64后仍限制在6MB内。
                limit = (
                    6 * 1024 * 1024
                    if scope["path"] in {"/api/invoices/import/preview", "/api/invoices/import/confirm"}
                    else 128 * 1024
                )
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    buffer.extend(message.get("body", b""))
                    if len(buffer) > limit:
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
            error_type = type(error).__name__
            if started:
                logger.error(
                    "response_failed method=%s route=%s type=%s",
                    scope["method"],
                    getattr(scope.get("route"), "path", "<unmatched>"),
                    error_type,
                )
                raise
            if isinstance(error, ApiError):
                status, message = error.status, error.message
            else:
                status, message = 500, "服务处理失败，请检查服务器配置"
            await JSONResponse({"error": message}, status_code=status)(scope, receive, secured)


def register_error_handlers(app):
    @app.exception_handler(ApiError)
    async def api_error(_request, error):
        return JSONResponse({"error": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _error):
        # 错误不回显密码、请求体和私有字段。
        for error in _error.errors():
            if error["type"] in {"ns_query_scope", "sync_date_range"}:
                # 此专用类型仅由查询DTO生成固定中文说明，不插入用户输入。
                return JSONResponse({"error": error["msg"]}, status_code=400)
        return JSONResponse({"error": "请求字段缺失、类型错误或包含多余字段"}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(_request, error):
        return JSONResponse(
            {"error": "接口不存在" if error.status_code == 404 else "不支持的请求方式"},
            status_code=error.status_code,
        )
