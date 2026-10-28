"""回写准备接口，不提供 execute/apply。"""

from typing import Annotated

from backend.core.dependencies import Owner
from fastapi import APIRouter, Path, Query

from ..dto.task_dto import ConfirmPlan, RevisionBody, TaskQuery

Id = Annotated[int, Path(ge=1, le=2**63 - 1)]


def create_router(tasks, queries):
    router = APIRouter(prefix="/api/writeback", tags=["回写准备"])

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

    @router.get("/invoices/{invoice_id}")
    def invoice(invoice_id: Id, owner: Owner):
        return tasks.invoice(invoice_id)

    @router.post("/invoices/{invoice_id}/recheck")
    def recheck(invoice_id: Id, owner: Owner):
        return tasks.recheck(invoice_id, owner)

    return router
