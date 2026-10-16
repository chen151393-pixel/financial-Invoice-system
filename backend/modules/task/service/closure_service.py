"""按差异结束是绑定依据与账本的人工决定，后续台账变化即失效。"""

from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import event_dao, task_dao, task_line_dao
from .progress_service import apply_receipt, refresh_task


class ClosureService:
    def __init__(self, engine, queries):
        self.engine, self.queries = engine, queries

    def close(self, task_id, line_id, body, actor):
        if actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能按差异结束")
        try:
            with transaction(self.engine) as connection:
                self._close(connection, task_id, line_id, body, actor)
        except SQLAlchemyError:
            raise ApiError(503, "差异结束结果未能确认，请刷新后核实，重试须沿用请求编号") from None
        return self.queries.detail(task_id)

    def _close(self, connection, task_id, line_id, body, actor):
        previous = event_dao.by_request(connection, str(body.requestId))
        if previous:
            if (previous["task_id"], previous["task_line_id"], previous["actor"], previous["reason"]) != (
                task_id,
                line_id,
                actor,
                body.reason,
            ):
                raise ApiError(409, "请求编号已用于其他决定")
            return
        task = task_dao.get(connection, task_id, lock=True)
        line = next((r for r in task_line_dao.by_tasks(connection, [task_id]) if r["id"] == line_id), None)
        if not task or not line:
            raise ApiError(404, "任务或任务行不存在")
        if line["status"] == "superseded" or line["requires_review"]:
            raise ApiError(409, "任务已被替代或有待复核占用，不能按差异结束")
        if (
            line["purchase_basis_id"] != int(body.purchaseBasisId)
            or line["ledger_sha256"] != body.ledgerSha256
        ):
            raise ApiError(409, "开票依据或分配账本已变化，请刷新后重新核实")
        stamp = datetime.now(timezone.utc).replace(tzinfo=None)
        details = {
            "purchaseBasisId": body.purchaseBasisId,
            "ledgerSha256": body.ledgerSha256,
            "quantityDifference": str(line["expected_quantity"] - line["received_quantity"])
            if line["expected_quantity"] is not None
            else None,
            "amountDifference": str(line["expected_amount"] - line["received_amount"])
            if line["expected_amount"] is not None
            else None,
        }
        event_id = event_dao.append(
            connection,
            {
                "task_id": task_id,
                "task_line_id": line_id,
                "from_status": task["status"],
                "to_status": task["status"],
                "reason": body.reason,
                "actor": actor,
                "event_type": "difference_closed",
                "details": details,
                "request_id": str(body.requestId),
            },
            stamp,
        )
        task_line_dao.update_progress(connection, line_id, {"closure_event_id": event_id}, stamp)
        apply_receipt(connection, line, line["received_quantity"], line["received_amount"], True, stamp)
        refresh_task(connection, task, actor, body.reason, stamp)
