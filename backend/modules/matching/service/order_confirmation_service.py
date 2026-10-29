"""整单确认：同一账本事务中保存全部明细，任何失败均回滚；请求重放须证据完全相同。"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid5

from backend.core.errors import ApiError

from ..dao import allocation_dao
from ..dto.matching_dto import ManualBody
from .order_candidate_service import candidates, digest


def confirm(service, body, actor):
    def action(connection):
        invoice_id = int(body.invoiceId)
        fingerprint = digest({"actor": actor, "body": body.model_dump(mode="json")})
        # 第一条分配使用整单 requestId，保存完整请求摘要；全事务提交保证不存在半单记录。
        existing = allocation_dao.by_request(connection, str(body.requestId))
        if existing:
            evidence = (existing["checks"] or {}).get("orderRequest")
            if evidence != fingerprint:
                raise ApiError(409, "请求编号已用于其他整单分配，不能复用")
            return existing["invoice_id"]
        found = candidates(connection, body, order_id=int(body.purchaseOrderId))
        if not found:
            raise ApiError(409, "整单候选已失效，请刷新后重新选择")
        candidate = found[0]
        if candidate.fingerprint != body.fingerprint:
            raise ApiError(409, "发票、采购来源或收票进度已变化，请刷新整单预览")
        if not candidate.confirm.allowed:
            raise ApiError(409, candidate.confirm.reason)
        if not body.note.strip():
            raise ApiError(400, "请填写整单审核说明，确认票面汇总与采购明细的对应依据")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for old in allocation_dao.by_invoices(connection, [invoice_id]):
            if old["status"] == "proposed":
                allocation_dao.update_status(
                    connection,
                    old["id"],
                    {
                        "status": "rejected",
                        "reviewed_by": actor,
                        "reviewed_at": now,
                        "review_note": "整单确认替代原待审核建议，原建议保留供追溯",
                    },
                    now,
                )
        for index, part in enumerate(candidate.allocations):
            request_id = body.requestId if index == 0 else uuid5(body.requestId, part.purchaseLineId)
            manual = ManualBody(
                requestId=request_id,
                invoiceId=body.invoiceId,
                invoiceItemId=part.invoiceItemId,
                purchaseLineId=part.purchaseLineId,
                purchaseBasisId=part.purchaseBasisId,
                invoiceVersionId=body.invoiceVersionId,
                quantity=Decimal(part.invoiceQuantity),
                amount=Decimal(part.amount),
                note=body.note,
                conversionNumerator=body.conversionNumerator,
                conversionDenominator=body.conversionDenominator,
                conversionEvidence=body.conversionEvidence,
            )
            service._manual(connection, manual, actor)
            saved = allocation_dao.by_request(connection, str(request_id))
            allocation_dao.update_status(
                connection,
                saved["id"],
                {
                    "checks": {
                        **(saved["checks"] or {}),
                        "orderRequest": fingerprint,
                        "orderId": body.purchaseOrderId,
                        "orderPreview": body.fingerprint,
                    }
                },
                now,
            )
        return invoice_id

    return service.queries.invoice(service._run(action, actor))
