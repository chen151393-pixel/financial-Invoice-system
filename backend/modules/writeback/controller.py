"""预览、确认执行与任务查询；旧协议保持兼容。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from .dto import ExecuteBody, PreviewBody, PreviewTextBody
from .vo import JobSummary, Preview, PreviewView


def create_router(service):
    router = APIRouter(prefix="/api/ns", tags=["回写"])

    @router.post("/preview", status_code=201, response_model=Preview)
    def preview(body: PreviewBody, owner: Owner):
        return service.preview(body.model_dump(), owner)

    @router.post("/preview-text", status_code=201, response_model=PreviewView)
    def preview_text(body: PreviewTextBody, owner: Owner):
        result = service.preview_text(body.model_dump(), owner)
        return service.describe(result["id"], owner)

    @router.post("/execute", response_model=Preview)
    def execute(body: ExecuteBody, owner: Owner):
        return service.execute_confirmed(body.previewId, body.confirm, owner)

    @router.get("/jobs", response_model=list[JobSummary])
    def jobs(owner: Owner):
        return service.list_jobs(owner)

    @router.get("/jobs/{preview_id}", response_model=Preview)
    def job(preview_id: str, owner: Owner):
        return service.get(preview_id, owner)

    @router.get("/jobs/{preview_id}/view", response_model=PreviewView)
    def view(preview_id: str, owner: Owner):
        return service.describe(preview_id, owner)

    return router
