"""取消原占用并建立新分配：同一事务，失败时原分配不动。"""

from datetime import datetime, timezone

from backend.core.errors import ApiError

from ..dao import allocation_dao
from . import ledger_service


def replace(service, allocation_id, body, actor):
    if actor.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能替换分配")

    def action(connection):
        previous = allocation_dao.by_request(connection, str(body.requestId))
        if previous:
            history = previous["verification_history"] or []
            if not any(h.get("replacesAllocationId") == allocation_id for h in history):
                raise ApiError(409, "请求编号已用于其他分配")
            return service._manual(connection, body, actor)
        old = allocation_dao.get(connection, allocation_id)
        if not old or old["status"] != "confirmed":
            raise ApiError(409, "只有已确认占用可以原子替换")
        ledger_service.prepare(
            connection,
            sorted({old["purchase_line_id"], int(body.purchaseLineId)}),
            sorted({old["invoice_id"], int(body.invoiceId)}),
        )
        stamp = datetime.now(timezone.utc).replace(tzinfo=None)
        allocation_dao.update_status(
            connection,
            allocation_id,
            {
                "status": "cancelled",
                "cancelled_by": actor,
                "cancelled_at": stamp,
                "cancel_reason": body.reason,
            },
            stamp,
        )
        # 新确认的剩余额度须排除刚撤销的原占用；仍在同一事务，后续失败会一起回滚。
        service._publish(connection, old["purchase_line_id"], actor, "替换时重新计算原占用")
        invoice_id = service._manual(connection, body, actor)
        created = allocation_dao.by_request(connection, str(body.requestId))
        history = created["verification_history"] + [
            {
                "action": "replacement",
                "replacesAllocationId": allocation_id,
                "reason": body.reason,
                "actor": actor,
                "at": stamp.isoformat(),
            }
        ]
        allocation_dao.update_status(connection, created["id"], {"verification_history": history}, stamp)
        for line_id in sorted({old["purchase_line_id"], created["purchase_line_id"]}):
            service._publish(connection, line_id, actor, "原分配已原子替换")
        return invoice_id, old["invoice_id"]

    return service.queries.invoice(service._run(action, actor))
