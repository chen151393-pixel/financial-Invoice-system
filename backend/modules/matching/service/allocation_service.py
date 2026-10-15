"""人工审核比对建议与分配（数据库设计第 7 节第 8 步）：通过、驳回、取消、人工新建、批量通过高置信度建议。

事务内加锁顺序：任务 → 任务行（task 门面）→ 发票（invoice 门面）→ 分配。通过或取消后在同一事务中发布
AllocationChanged，task 订阅后重算收票进度；任何一步失败整体回滚。
"""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import lock_invoice, read_invoices
from backend.modules.source.public import purchase_lines
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..policy import allocation_policy as rules
from ..policy.comparison_policy import HIGH, compare
from ..public import AllocationChanged, LineReceipt


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _require_user(actor):
    if actor.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能审核发票比对")


class AllocationService:
    def __init__(self, engine, events, queries):
        self.engine, self.events, self.queries = engine, events, queries

    def _run(self, action):
        try:
            with self.engine.begin() as connection:
                return action(connection)
        except IntegrityError:
            raise ApiError(409, "该发票行与子采购行已有有效记录，请刷新后核对") from None
        except SQLAlchemyError:
            raise ApiError(503, "比对结果暂无法确认，请刷新后查看；同一请求重复提交不会重复分配") from None

    def _context(self, connection, allocation):
        """锁定并读取审核所需的全部上下文。"""
        purchase_line_id, invoice_id = allocation["purchase_line_id"], allocation["invoice_id"]
        task_lines = open_lines(connection, [purchase_line_id], lock=True)
        lock_invoice(connection, invoice_id)
        found = read_invoices(connection, [invoice_id])
        item = (
            next((row for row in found[0]["items"] if row["id"] == allocation["invoice_item_id"]), None)
            if found
            else None
        )
        if item is None:
            raise ApiError(404, "发票行不存在或不属于该发票")
        invoice = found[0]
        line = purchase_lines(connection, [purchase_line_id]).get(purchase_line_id)
        return invoice, item, line, task_lines[0] if task_lines else None

    def _publish(self, connection, purchase_line_id, actor, reason):
        totals = allocation_dao.confirmed_by_purchase_lines(connection, [purchase_line_id])
        quantity, amount, closed = totals.get(purchase_line_id, (0, 0, False))
        receipt = LineReceipt(
            purchase_line_id=purchase_line_id, quantity=quantity, amount=amount, closed=closed
        )
        self.events.publish(connection, AllocationChanged(receipts=(receipt,), actor=actor, reason=reason))

    def _approve(self, connection, allocation, note, closes_line, actor, now):
        """通过一条分配（建议或人工新建）：校验硬性条件、容量与说明，更新并发布事件。"""
        invoice, item, line, task_line = self._context(connection, allocation)
        block = rules.hard_block(invoice, line, task_line)
        if (
            not block
            and allocation["checks"]
            and line["digest"] != allocation["checks"].get("purchaseDigest")
        ):
            block = "子采购行内容在建议生成后已变化，比对依据过期，请重新生成建议"
        if not block:
            used = allocation_dao.confirmed_by_item(connection, item["id"], exclude_id=allocation["id"])
            block = rules.capacity_block(item, *used, allocation["quantity"], allocation["amount"])
        if block:
            raise ApiError(409, block)
        checks, _ = compare(invoice, item, line, *rules.remaining(task_line))
        exceeds = rules.exceeds_expected(task_line, allocation["quantity"], allocation["amount"])
        reasons = rules.note_reasons(checks, exceeds, closes_line)
        if reasons and not note:
            raise ApiError(400, "请填写审核说明：" + "、".join(reasons))
        allocation_dao.update_status(
            connection,
            allocation["id"],
            {
                "status": "confirmed",
                "exceeds_expected": exceeds,
                "closes_purchase_line": closes_line,
                "reviewed_by": actor,
                "reviewed_at": now,
                "review_note": note or None,
            },
            now,
        )
        self._publish(
            connection, allocation["purchase_line_id"], actor, f"发票 {invoice['invoice_no']} 比对通过"
        )

    def confirm(self, allocation_id, body, actor):
        _require_user(actor)

        def action(connection):
            allocation = allocation_dao.get(connection, allocation_id)
            if allocation is None:
                raise ApiError(404, "比对记录不存在")
            current = allocation_dao.get(connection, allocation_id, lock=True)
            if current["status"] == "confirmed" and current["reviewed_by"] == actor:
                return current["invoice_id"]  # 同一操作重复提交，返回原结果
            if current["status"] != "proposed":
                raise ApiError(409, f"该记录{rules.STATUS_LABELS[current['status']]}，请刷新后核对")
            self._approve(connection, current, body.note.strip(), body.closesPurchaseLine, actor, _now())
            return current["invoice_id"]

        return self.queries.invoice(self._run(action))

    def reject(self, allocation_id, body, actor):
        _require_user(actor)

        def action(connection):
            current = allocation_dao.get(connection, allocation_id, lock=True)
            if current is None:
                raise ApiError(404, "比对记录不存在")
            if current["status"] == "proposed":
                now = _now()
                values = {"status": "rejected", "reviewed_by": actor, "reviewed_at": now}
                allocation_dao.update_status(
                    connection, allocation_id, values | {"review_note": body.note.strip() or None}, now
                )
            elif current["status"] != "rejected":
                raise ApiError(409, f"该记录{rules.STATUS_LABELS[current['status']]}，不能驳回")
            return current["invoice_id"]

        return self.queries.invoice(self._run(action))

    def cancel(self, allocation_id, body, actor):
        _require_user(actor)

        def action(connection):
            allocation = allocation_dao.get(connection, allocation_id)
            if allocation is None:
                raise ApiError(404, "比对记录不存在")
            open_lines(connection, [allocation["purchase_line_id"]], lock=True)
            lock_invoice(connection, allocation["invoice_id"])
            current = allocation_dao.get(connection, allocation_id, lock=True)
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

        return self.queries.invoice(self._run(action))

    def create_manual(self, body, actor):
        """人工新建分配并直接通过（置信度为空）；requestId 保证重复提交只生效一次。"""
        _require_user(actor)

        def action(connection):
            existing = allocation_dao.by_request(connection, str(body.requestId))
            if existing is not None:
                return existing["invoice_id"]
            invoice_id, item_id = int(body.invoiceId), int(body.invoiceItemId)
            purchase_line_id = int(body.purchaseLineId)
            # 先按顺序加锁（任务 → 任务行 → 发票），再写入分配。
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
            self._approve(connection, allocation, body.note.strip(), body.closesPurchaseLine, actor, now)
            return invoice_id

        return self.queries.invoice(self._run(action))

    def confirm_batch(self, body, actor):
        """批量通过高置信度且无需说明的建议；逐条独立事务，返回通过与跳过数量及原因。"""
        _require_user(actor)
        confirmed, skipped = 0, []
        for allocation_id in dict.fromkeys(int(value) for value in body.ids):

            def action(connection, allocation_id=allocation_id):
                current = allocation_dao.get(connection, allocation_id)
                if current is None or current["status"] != "proposed":
                    raise ApiError(409, "记录不存在或不是待审核建议")
                if current["confidence"] is None or current["confidence"] < HIGH:
                    raise ApiError(409, "置信度未达到高档，请逐条审核")
                self._approve(
                    connection,
                    allocation_dao.get(connection, allocation_id, lock=True),
                    "",
                    False,
                    actor,
                    _now(),
                )

            try:
                self._run(action)
                confirmed += 1
            except ApiError as error:
                skipped.append({"id": str(allocation_id), "reason": error.message})
        return {"confirmed": confirmed, "skipped": skipped}
