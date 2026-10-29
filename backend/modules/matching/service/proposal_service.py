"""生成比对建议：汇总票优先整单分配，否则保留逐行建议供人工核实。

- 候选只来自有效任务行（已审核的应开范围）；优先备注命中的子单或母单所属子单，未命中才按供应商召回。
- 导入事件不覆盖已有建议；手工重新生成可替换变化的待审建议，已通过分配不动。
- 建议全部要人工审核；整单方案按采购明细拆分数量金额，保留票面原始行。
- on_invoices_imported 订阅 invoice 的 InvoicesImported，在导入事务中执行；generate_now 供页面重新生成。
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.invoice.public import read_invoices
from backend.modules.review.public import current_bases
from backend.modules.source.public import purchase_lines
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..policy.allocation_policy import SYSTEM, remaining
from ..policy.comparison_policy import compare, name_result, order_reference
from .order_proposal_service import expected_order_parts


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def recalled(invoice, line):
    """订单命中不受供应商名称差异限制；无订单命中时允许名称相同 / 包含的候选。"""
    if order_reference(invoice["remark"], line):
        return True
    return name_result(invoice["seller_name_normalized"], line["supplier_name_normalized"]) in (
        "match",
        "partial",
    )


def best_candidate(invoice, item, task_lines, contexts):
    best = None
    best_rank = None
    for task_line in task_lines:
        line = contexts.get(task_line["purchase_line_id"])
        if line is None or not line["active"] or not recalled(invoice, line):
            continue
        checks, confidence = compare(invoice, item, line, *remaining(task_line))
        # 单号决定优先范围，不允许其他订单仅凭供应商等字段得分更高而抢占建议。
        rank = (bool(order_reference(invoice["remark"], line)), confidence)
        if best_rank is None or rank > best_rank:
            best = (task_line, line, confidence, checks)
            best_rank = rank
    return best


def generate(connection, invoice_ids, actor, *, refresh=False):
    """在调用方事务中生成建议，返回新增条数。"""
    invoices = [
        invoice for invoice in read_invoices(connection, invoice_ids) if invoice["status"] == "normal"
    ]
    item_ids = [item["id"] for invoice in invoices for item in invoice["items"]]
    if not item_ids:
        return 0
    active = {}
    for row in allocation_dao.by_invoices(connection, invoice_ids):
        if row["status"] in ("proposed", "confirmed"):
            active.setdefault(row["invoice_item_id"], []).append(row)
    task_lines = open_lines(connection)
    contexts = purchase_lines(connection, [line["purchase_line_id"] for line in task_lines])
    bases = current_bases(connection, list(contexts))
    for line_id, line in contexts.items():
        basis = bases.get(line_id)
        line.update(currency=basis["currency"] if basis else None)
    now, created = _now(), 0
    for invoice in invoices:
        for item in invoice["items"]:
            previous = active.get(item["id"], [])
            if (
                not item["is_active"]
                or invoice["detail_status"] != "complete"
                or any(row["status"] == "confirmed" for row in previous)
                or (previous and not refresh)
            ):
                continue
            best = best_candidate(invoice, item, task_lines, contexts)
            if best is None:
                continue
            task_line, line, confidence, checks = best
            expected = {
                "purchase_line_id": task_line["purchase_line_id"],
                "purchase_basis_id": task_line["purchase_basis_id"],
                "invoice_version_id": invoice["current_version_id"],
                "quantity": item["quantity"] if item["quantity"] is not None else Decimal(0),
                "amount": item["amount_including_tax"] or Decimal(0),
                "confidence": confidence,
                "checks": {"items": checks, "purchaseDigest": line["digest"]},
            }
            expected_rows = expected_order_parts(connection, invoice, item, contexts, task_lines) or [
                expected
            ]
            old_by_line = {row["purchase_line_id"]: row for row in previous}
            if len(previous) == len(expected_rows) and all(
                all(
                    old_by_line.get(row["purchase_line_id"], {}).get(key) == value
                    for key, value in row.items()
                )
                for row in expected_rows
            ):
                continue
            # 与新建议同事务保存；插入失败时旧建议仍有效，不覆盖历史或已确认分配。
            for row in previous:
                allocation_dao.update_status(
                    connection,
                    row["id"],
                    {
                        "status": "rejected",
                        "reviewed_by": actor,
                        "reviewed_at": now,
                        "review_note": "重新生成建议：候选或比对依据已变化，旧待审建议由新建议替代",
                    },
                    now,
                )
            for expected_row in expected_rows:
                allocation_dao.insert_allocation(
                    connection,
                    {
                        "invoice_id": invoice["id"],
                        "invoice_item_id": item["id"],
                        **expected_row,
                        "status": "proposed",
                        "proposed_by": actor,
                        "proposed_at": now,
                        "request_id": str(uuid.uuid4()),
                    },
                    now,
                )
                created += 1
    return created


def on_invoices_imported(connection, event):
    generate(connection, list(event.invoice_ids), SYSTEM)


class ProposalService:
    def __init__(self, engine):
        self.engine = engine

    def generate_now(self, invoice_ids, actor):
        """页面"重新生成建议"：用于发票先导入、报关单后审核的情况。"""
        if actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能生成比对建议")
        try:
            with transaction(self.engine) as connection:
                return generate(connection, invoice_ids, actor, refresh=True)
        except SQLAlchemyError:
            raise ApiError(503, "比对建议生成失败，请稍后重试") from None
