"""同域静态页面服务；拒绝路径越界和隐藏文件。"""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .errors import ApiError


def create_router(settings):
    router = APIRouter()

    @router.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise ApiError(404, "接口不存在")
        if any(part.startswith(".") for part in path.replace("\\", "/").split("/")):
            raise ApiError(404, "文件不存在")
        root = settings.web_root.resolve()
        file = (root / path).resolve()
        if not file.is_relative_to(root):
            raise ApiError(404, "文件不存在")
        if not file.is_file():
            if file.suffix:
                raise ApiError(404, "文件不存在")
            file = root / "index.html"
        if not file.is_file():
            raise ApiError(503, "请先执行 npm run build 构建前端（产物位于 frontend/dist）")
        return FileResponse(file)

    return router
