"""人工审核比对建议与分配（数据库设计第 7 节第 8 步）：通过、驳回、取消、人工新建、批量通过高置信度建议。

事务内加锁顺序：任务 → 任务行（task 门面）→ 发票（invoice 门面）→ 分配。通过或取消后在同一事务中发布
AllocationChanged，task 订阅后重算收票进度；任何一步失败整体回滚。
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.invoice.public import lock_invoice
from backend.modules.review.public import current_bases
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..dto.matching_dto import ConfirmBody
from ..policy import allocation_policy as rules
from ..policy.comparison_policy import HIGH
from ..public import InvoiceMatchingChanged
from . import approval_service, group_view_service, ledger_service
from .group_view_service import GroupBatch, group_id


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _require_user(actor):
    if actor.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能审核发票比对")


class AllocationService:
    def __init__(self, engine, events, queries):
        self.engine, self.events, self.queries = engine, events, queries

    def _run(self, action, actor):
        try:
            with transaction(self.engine) as connection:
                result = action(connection)
                invoice_ids = result if isinstance(result, tuple) else (result,)
                self.events.publish(connection, InvoiceMatchingChanged(invoice_ids, actor, "分配操作已完成"))
                return invoice_ids[0]
        except IntegrityError:
            raise ApiError(409, "该发票行与子采购行已有有效记录，请刷新后核对") from None
        except SQLAlchemyError:
            raise ApiError(503, "比对结果暂无法确认，请刷新后查看；同一请求重复提交不会重复分配") from None

    def _publish(self, connection, purchase_line_id, actor, reason):
        ledger_service.publish(connection, [purchase_line_id], self.events, actor, reason)

    def confirm_order(self, body, actor):
        from .order_confirmation_service import confirm

        _require_user(actor)
        return confirm(self, body, actor)

    def confirm_group(self, key, body, actor):
        _require_user(actor)
        return self.queries.invoice(group_view_service.confirm(self, key, body, actor))

    def reject_group(self, key, body, actor):
        _require_user(actor)
        return self.queries.invoice(group_view_service.reject(self, key, body, actor))

    def _approve(self, connection, allocation, body, actor, now, *, reverify=False):
        return approval_service.approve(self, connection, allocation, body, actor, now, reverify=reverify)

    def replace(self, allocation_id, body, actor):
        from .replacement_service import replace

        return replace(self, allocation_id, body, actor)

    def reverify(self, allocation_id, body, actor):
        _require_user(actor)

        def action(connection):
            current = allocation_dao.get(connection, allocation_id)
            if not current or current["status"] != "confirmed":
                raise ApiError(409, "只有已确认分配可以重新核实")
            self._approve(connection, current, body, actor, _now(), reverify=True)
            return current["invoice_id"]

        return self.queries.invoice(self._run(action, actor))

    def confirm(self, allocation_id, body, actor):
        _require_user(actor)

        def action(connection):
            allocation = allocation_dao.get(connection, allocation_id)
            if allocation is None:
                raise ApiError(404, "比对记录不存在")
            current = allocation_dao.get(connection, allocation_id)
            if current["status"] == "confirmed" and current["reviewed_by"] == actor:
                return current["invoice_id"]  # 同一操作重复提交，返回原结果
            if current["status"] != "proposed":
                raise ApiError(409, f"该记录{rules.STATUS_LABELS[current['status']]}，请刷新后核对")
            if group_id(current):
                raise ApiError(409, "整单建议须整组通过，请在发票比对详情中审核整单")
            self._approve(connection, current, body, actor, _now())
            return current["invoice_id"]

        return self.queries.invoice(self._run(action, actor))

    def reject(self, allocation_id, body, actor):
        _require_user(actor)

        def action(connection):
            current = allocation_dao.get(connection, allocation_id)
            if current is None:
                raise ApiError(404, "比对记录不存在")
            if current["status"] == "proposed" and group_id(current):
                raise ApiError(409, "整单建议须整组驳回，请在发票比对详情中处理整单")
            if current["status"] == "proposed":
                now = _now()
                values = {"status": "rejected", "reviewed_by": actor, "reviewed_at": now}
                allocation_dao.update_status(
                    connection, allocation_id, values | {"review_note": body.note.strip() or None}, now
                )
            elif current["status"] != "rejected":
                raise ApiError(409, f"该记录{rules.STATUS_LABELS[current['status']]}，不能驳回")
            return current["invoice_id"]

        return self.queries.invoice(self._run(action, actor))

    def cancel(self, allocation_id, body, actor):
        _require_user(actor)

        def action(connection):
            allocation = allocation_dao.get(connection, allocation_id)
            if allocation is None:
                raise ApiError(404, "比对记录不存在")
            current_bases(connection, [allocation["purchase_line_id"]], lock=True)
            open_lines(connection, [allocation["purchase_line_id"]], lock=True)
            lock_invoice(connection, allocation["invoice_id"])
            current = allocation_dao.get(connection, allocation_id)
            if current["status"] == "cancelled":
                return current["invoice_id"]
            if current["status"] != "confirmed":
                raise ApiError(409, "只有已通过的分配可以取消")
            now = _now()
            values = {
                "status": "cancelled",
                "cancelled_by": actor,
                "cancelled_at": now,
                "cancel_reason": body.reason.strip(),
            }
            allocation_dao.update_status(connection, allocation_id, values, now)
            self._publish(connection, current["purchase_line_id"], actor, f"取消分配：{body.reason.strip()}")
            return current["invoice_id"]

        return self.queries.invoice(self._run(action, actor))

    def create_manual(self, body, actor):
        """人工新建分配并直接通过（置信度为空）；requestId 保证重复提交只生效一次。"""
        _require_user(actor)

        return self.queries.invoice(
            self._run(lambda connection: self._manual(connection, body, actor), actor)
        )

    def _manual(self, connection, body, actor):
        fingerprint = hashlib.sha256((actor + body.model_dump_json()).encode()).hexdigest()
        existing = allocation_dao.by_request(connection, str(body.requestId))
        if existing is not None:
            _verify_replay(existing, body, actor, fingerprint)
            return existing["invoice_id"]
        invoice_id, item_id = int(body.invoiceId), int(body.invoiceItemId)
        purchase_line_id = int(body.purchaseLineId)
        # 先按顺序加锁（任务 → 任务行 → 发票），再写入分配。
        current_bases(connection, [purchase_line_id], lock=True)
        open_lines(connection, [purchase_line_id], lock=True)
        lock_invoice(connection, invoice_id)
        now = _now()
        allocation_id = allocation_dao.insert_allocation(
            connection,
            {
                "invoice_id": invoice_id,
                "invoice_item_id": item_id,
                "purchase_line_id": purchase_line_id,
                "quantity": body.quantity,
                "amount": body.amount,
                "status": "proposed",
                "confidence": None,
                "checks": None,
                "proposed_by": actor,
                "proposed_at": now,
                "request_id": str(body.requestId),
            },
            now,
        )
        allocation = allocation_dao.get(connection, allocation_id)
        self._approve(connection, allocation, body, actor, now)
        saved = allocation_dao.get(connection, allocation_id)
        history = saved["verification_history"]
        history[0]["requestFingerprint"] = fingerprint
        allocation_dao.update_status(connection, allocation_id, {"verification_history": history}, now)
        self._publish(connection, purchase_line_id, actor, "人工分配证据已保存")
        return invoice_id

    def confirm_batch(self, body, actor):
        """批量通过高置信度且无需说明的建议；逐条独立事务，返回通过与跳过数量及原因。"""
        _require_user(actor)
        confirmed, skipped = 0, []
        groups = GroupBatch(self.engine, body.ids)
        for key, invoice_id, ids in groups.items:
            # 整单建议整组通过；组内任一条不满足条件时整组跳过，不会只通过部分明细。
            try:
                group_view_service.confirm(self, key, GroupBatch.body(invoice_id), actor, batch=True)
                confirmed += len(ids)
            except ApiError as error:
                skipped += [{"id": value, "reason": error.message} for value in ids]
        for allocation_id in dict.fromkeys(int(value) for value in body.ids if value not in groups.ids):

            def action(connection, allocation_id=allocation_id):
                current = allocation_dao.get(connection, allocation_id)
                if current is None or current["status"] != "proposed":
                    raise ApiError(409, "记录不存在或不是待审核建议")
                if current["confidence"] is None or current["confidence"] < HIGH:
                    raise ApiError(409, "置信度未达到高档，请逐条审核")
                self._approve(
                    connection,
                    allocation_dao.get(connection, allocation_id),
                    ConfirmBody(),
                    actor,
                    _now(),
                )
                return current["invoice_id"]

            try:
                self._run(action, actor)
                confirmed += 1
            except ApiError as error:
                skipped.append({"id": str(allocation_id), "reason": error.message})
        return {"confirmed": confirmed, "skipped": skipped}


def _verify_replay(existing, body, actor, fingerprint):
    expected = (
        int(body.invoiceId),
        int(body.invoiceItemId),
        int(body.purchaseLineId),
        body.quantity,
        body.amount,
        actor,
    )
    actual = tuple(
        existing[k]
        for k in (
            "invoice_id",
            "invoice_item_id",
            "purchase_line_id",
            "quantity",
            "amount",
            "proposed_by",
        )
    )
    original = next(
        (
            h.get("requestFingerprint")
            for h in existing["verification_history"] or []
            if h.get("requestFingerprint")
        ),
        None,
    )
    if actual != expected or (original and original != fingerprint):
        raise ApiError(409, "请求编号已用于其他分配，不能复用")
