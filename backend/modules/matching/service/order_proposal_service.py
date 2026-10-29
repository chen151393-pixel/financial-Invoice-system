"""汇总票优先生成整单明细建议，不能把整票数量金额塞进某一采购行。"""

from decimal import Decimal

from ..dto.order_matching_dto import OrderCandidateQuery
from ..policy.allocation_policy import remaining
from ..policy.comparison_policy import compare
from .order_candidate_service import candidates


def expected_order_parts(connection, invoice, item, contexts, task_lines):
    if sum(row["is_active"] for row in invoice["items"]) != 1:
        return None
    found = candidates(connection, OrderCandidateQuery(invoiceId=str(invoice["id"])))
    matched = [row for row in found if row.orderMatched]
    eligible = [row for row in (matched or found) if row.confirm.allowed]
    # 母单关联多个同等候选时交由用户选择，不任意选一张子单。
    if len(eligible) != 1 or len(eligible[0].allocations) <= 1:
        return None
    tasks = {row["purchase_line_id"]: row for row in task_lines}
    result = []
    for part in eligible[0].allocations:
        line_id = int(part.purchaseLineId)
        line, task = contexts[line_id], tasks[line_id]
        compared = {
            **item,
            "quantity": Decimal(part.invoiceQuantity),
            "amount_including_tax": Decimal(part.amount),
        }
        if item.get("amount_excluding_tax") is not None and item["amount_including_tax"]:
            compared["amount_excluding_tax"] = (
                item["amount_excluding_tax"] * compared["amount_including_tax"] / item["amount_including_tax"]
            )
        checks, confidence = compare(invoice, compared, line, *remaining(task))
        result.append(
            {
                "purchase_line_id": line_id,
                "purchase_basis_id": task["purchase_basis_id"],
                "invoice_version_id": invoice["current_version_id"],
                "quantity": compared["quantity"],
                "amount": compared["amount_including_tax"],
                "confidence": confidence,
                "checks": {
                    "items": checks,
                    "purchaseDigest": line["digest"],
                    "scope": "whole_order",
                    "orderId": eligible[0].purchaseOrderId,
                },
            }
        )
    return result
