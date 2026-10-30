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
        close_line(connection, task, line, actor, body.reason, str(body.requestId), stamp)


def close_line(connection, task, line, actor, reason, request_id, stamp):
    """追加 difference_closed 事件并把任务行标为按差异结束；调用方已锁定任务与任务行。"""
    details = {
        "purchaseBasisId": str(line["purchase_basis_id"]),
        "ledgerSha256": line["ledger_sha256"],
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
            "task_id": task["id"],
            "task_line_id": line["id"],
            "from_status": task["status"],
            "to_status": task["status"],
            "reason": reason,
            "actor": actor,
            "event_type": "difference_closed",
            "details": details,
            "request_id": request_id,
        },
        stamp,
    )
    task_line_dao.update_progress(connection, line["id"], {"closure_event_id": event_id}, stamp)
    apply_receipt(connection, line, line["received_quantity"], line["received_amount"], True, stamp)
    refresh_task(connection, task, actor, reason, stamp)


def on_lines_closed_by_difference(connection, event):
    """整单关联确认时发票少于子采购单：同一比对事务内按差异结束这些子采购明细。

    任务行须仍是确认时的开票依据且没有待复核占用；条件不满足时抛错，整个比对事务回滚。
    """
    stamp = datetime.now(timezone.utc).replace(tzinfo=None)
    purchase_ids = [line.purchase_line_id for line in event.lines]
    found = task_line_dao.active_by_purchase_lines(connection, purchase_ids)
    # 加锁顺序：任务 → 任务行（后端规则第 7 节）
    task_dao.by_ids(connection, sorted({row["task_id"] for row in found}), lock=True)
    lines = {
        row["purchase_line_id"]: row
        for row in task_line_dao.active_by_purchase_lines(connection, purchase_ids, lock=True)
    }
    for closed in event.lines:
        if event_dao.by_request(connection, closed.request_id):
            continue
        line = lines.get(closed.purchase_line_id)
        if line is None or line["purchase_basis_id"] != closed.purchase_basis_id or line["requires_review"]:
            raise ApiError(409, "子采购明细的开票依据已变化或有待复核占用，不能按差异结束，请刷新后核对")
        # 同一任务多行结束时每次读取最新任务状态，避免状态流转按旧值记录
        task = task_dao.get(connection, line["task_id"], lock=True)
        close_line(connection, task, line, event.actor, event.reason, closed.request_id, stamp)
