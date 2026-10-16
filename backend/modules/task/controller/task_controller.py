"""开票跟进接口：任务列表、详情、保存合同、通知草稿与人工发送登记。"""

from typing import Annotated

from fastapi import APIRouter, Path

from backend.core.dependencies import Owner

from ..dto.notification_dto import NotificationDraft, NotificationRecord
from ..dto.task_dto import ClosureRequest, TaskListQuery
from ..vo.task_vo import TaskDetail, TaskList

Id = Annotated[int, Path(ge=1, le=2**63 - 1)]


def create_router(tasks, documents, notifications, closures):
    router = APIRouter(prefix="/api/tasks", tags=["开票跟进"])

    @router.post("/query", response_model=TaskList)
    def query(body: TaskListQuery, owner: Owner):
        return tasks.browse(body)

    @router.get("/{task_id}", response_model=TaskDetail)
    def detail(task_id: Id, owner: Owner):
        return tasks.detail(task_id)

    @router.post("/{task_id}/documents/{order_id}/prepare", response_model=TaskDetail)
    def prepare(task_id: Id, order_id: Id, owner: Owner):
        return documents.prepare(task_id, order_id, owner)

    @router.post("/{task_id}/notification/draft", response_model=TaskDetail)
    def save_notification(task_id: Id, body: NotificationDraft, owner: Owner):
        return notifications.save_draft(task_id, body, owner)

    @router.post("/{task_id}/notification/record", response_model=TaskDetail)
    def record_notification(task_id: Id, body: NotificationRecord, owner: Owner):
        return notifications.record(task_id, body, owner)

    @router.post("/{task_id}/lines/{line_id}/close", response_model=TaskDetail)
    def close(task_id: Id, line_id: Id, body: ClosureRequest, owner: Owner):
        return closures.close(task_id, line_id, body, owner)

    return router
