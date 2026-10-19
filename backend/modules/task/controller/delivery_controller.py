"""开票任务企微通知资源接口，认证和业务规则由服务端执行。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.delivery_dto import (
    DeliveryPreviewRequest,
    DeliveryReconcileRequest,
    DeliveryRefreshRequest,
    DeliverySubmitRequest,
)
from ..vo.delivery_vo import DeliveryCandidates, DeliveryList, DeliveryPreview, DeliveryView
from .task_controller import Id


def create_router(submissions, receipts, reconciliations):
    router = APIRouter(prefix="/api/tasks", tags=["企微开票通知"])

    @router.post("/{task_id}/notification/preview", response_model=DeliveryPreview)
    def preview(task_id: Id, body: DeliveryPreviewRequest, owner: Owner):
        return submissions.preview(task_id, body, owner)

    @router.post("/{task_id}/notification/submit", response_model=DeliveryView)
    def submit(task_id: Id, body: DeliverySubmitRequest, owner: Owner):
        return submissions.submit(task_id, body, owner)

    @router.get("/{task_id}/notification/delivery", response_model=DeliveryList)
    def deliveries(task_id: Id, owner: Owner):
        return receipts.history(task_id)

    @router.post("/{task_id}/notification/refresh", response_model=DeliveryView)
    def refresh(task_id: Id, body: DeliveryRefreshRequest, owner: Owner):
        return receipts.refresh(task_id, body, owner)

    @router.get(
        "/{task_id}/notification/delivery/{delivery_id}/candidates", response_model=DeliveryCandidates
    )
    def candidates(task_id: Id, delivery_id: Id, owner: Owner):
        return reconciliations.candidates(task_id, delivery_id, owner)

    @router.post("/{task_id}/notification/reconcile", response_model=DeliveryView)
    def reconcile(task_id: Id, body: DeliveryReconcileRequest, owner: Owner):
        return reconciliations.reconcile(task_id, body, owner)

    return router
