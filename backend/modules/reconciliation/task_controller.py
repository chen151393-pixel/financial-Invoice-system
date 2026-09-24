"""开票跟进查询、获取采购原件及授权文件下载。"""

from uuid import UUID

from fastapi import APIRouter

from backend.core.dependencies import Owner

from .dto import TaskListQuery
from .notification_dto import NotificationDraft, NotificationRecord
from .task_vo import TaskDetail, TaskList


def create_router(service):
    router = APIRouter(prefix="/api/reconciliation/invoice-tasks", tags=["开票跟进"])

    @router.post("/query", response_model=TaskList)
    def query(body: TaskListQuery, owner: Owner):
        return service.browse(body, owner)

    @router.get("/{task_id}", response_model=TaskDetail)
    def detail(task_id: UUID, owner: Owner):
        return service.detail(str(task_id), owner)

    @router.post("/{task_id}/documents/{order_id}/prepare", response_model=TaskDetail)
    def prepare(task_id: UUID, order_id: str, owner: Owner):
        return service.prepare_document(str(task_id), order_id, owner)

    @router.post("/{task_id}/notification/draft", response_model=TaskDetail)
    def save_notification(task_id: UUID, body: NotificationDraft, owner: Owner):
        return service.save_notification(str(task_id), body, owner)

    @router.post("/{task_id}/notification/record", response_model=TaskDetail)
    def record_notification(task_id: UUID, body: NotificationRecord, owner: Owner):
        return service.save_notification(str(task_id), body, owner, record=True)

    return router
