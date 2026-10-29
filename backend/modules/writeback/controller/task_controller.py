"""回写任务接口：准备、确认方案与预览、写入 NS 及结果不明时的人工核实。"""

from typing import Annotated

from backend.core.dependencies import Owner
from fastapi import APIRouter, Path, Query

from ..dto.task_dto import ConfirmPlan, ConfirmPreview, ResolveWrite, RevisionBody, TaskQuery

Id = Annotated[int, Path(ge=1, le=2**63 - 1)]


def create_router(tasks, queries, executor):
    router = APIRouter(prefix="/api/writeback", tags=["NS 回写"])

    @router.get("/tasks")
    def listing(criteria: Annotated[TaskQuery, Query()], owner: Owner):
        return tasks.list(criteria)

    @router.get("/tasks/{task_id}")
    def detail(task_id: Id, owner: Owner):
        return tasks.get(task_id)

    @router.post("/tasks/{task_id}/refresh")
    def refresh(task_id: Id, body: RevisionBody, owner: Owner):
        return queries.refresh(task_id, body.revision, owner)

    @router.post("/tasks/{task_id}/confirm")
    def confirm(task_id: Id, body: ConfirmPlan, owner: Owner):
        return tasks.confirm(task_id, body, owner)

    @router.post("/tasks/{task_id}/preview/confirm")
    def confirm_preview(task_id: Id, body: ConfirmPreview, owner: Owner):
        return executor.confirm_preview(task_id, body, owner)

    @router.post("/tasks/{task_id}/execute")
    def execute(task_id: Id, body: RevisionBody, owner: Owner):
        return executor.execute(task_id, body.revision, owner)

    @router.post("/tasks/{task_id}/resolve")
    def resolve(task_id: Id, body: ResolveWrite, owner: Owner):
        return executor.resolve(task_id, body, owner)

    @router.get("/invoices/{invoice_id}")
    def invoice(invoice_id: Id, owner: Owner):
        return tasks.invoice(invoice_id)

    @router.post("/invoices/{invoice_id}/recheck")
    def recheck(invoice_id: Id, owner: Owner):
        return tasks.recheck(invoice_id, owner)

    return router
