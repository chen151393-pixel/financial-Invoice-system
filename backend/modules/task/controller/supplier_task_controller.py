"""供应商合并办理接口；参数校验及写入规则均由对应 Service 执行。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.supplier_task_dto import SupplierNotificationDraft, SupplierNotificationRecord
from ..vo.task_vo import TaskDetail
from .task_controller import Id


def create_router(groups, notifications):
    router = APIRouter(prefix="/api/task/supplier-tasks", tags=["供应商合并开票任务"])

    @router.get("/{task_id}", response_model=TaskDetail)
    def detail(task_id: Id, owner: Owner, completed: bool = False):
        return groups.detail(task_id, completed=completed)

    @router.post("/{task_id}/notification/draft", response_model=TaskDetail)
    def save(task_id: Id, body: SupplierNotificationDraft, owner: Owner):
        return notifications.save_draft(task_id, body, owner)

    @router.post("/{task_id}/notification/record", response_model=TaskDetail)
    def record(task_id: Id, body: SupplierNotificationRecord, owner: Owner):
        return notifications.record(task_id, body, owner)

    return router
