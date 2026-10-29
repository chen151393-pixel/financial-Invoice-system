"""生成比对建议：发票行对应一张或多张整张子采购单，不拆分子采购明细行（2026-10-29）。

- 候选只来自有效任务行（已审核的应开范围）；单号命中及供应商相近共同召回。
- 按符合项累加置信度，默认生成最高分整单方案；金额、单位或品名不符仍可展示待审核建议。
  不能超出发票可分配容量，最高分并列不猜配；人工确认时仍执行原有校验。
- 同一组建议共用 checks.group（组 ID 与子采购单 ID），审核时整组通过或驳回；每条子采购明细仍单独记账，
  供开票任务按行计算收票进度。
- 导入事件不覆盖已有建议；手工重新生成可替换变化的待审建议，已通过分配不动。
- on_invoices_imported 订阅 invoice 的 InvoicesImported，在导入事务中执行；generate_now 供页面重新生成。
"""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.invoice.public import read_invoices
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..policy.allocation_policy import SYSTEM
from . import group_plan_service

# 比较新旧建议是否相同的字段；相同时不重复追加。
_SAME = (
    "invoice_item_id",
    "purchase_line_id",
    "purchase_basis_id",
    "invoice_version_id",
    "quantity",
    "amount",
    "confidence",
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _unchanged(previous, expected):
    """金额、数量、版本、置信度与整单比对项都相同才视为未变化；比对项变化（如汇率、税率补齐）时替换旧建议。"""

    def key(row):
        return (
            *(row[name] for name in _SAME),
            json.dumps((row["checks"] or {}).get("items"), sort_keys=True, default=str),
        )

    return sorted(map(key, previous)) == sorted(map(key, expected))


def generate(connection, invoice_ids, actor, *, refresh=False):
    """在调用方事务中生成建议，返回新增条数。"""
    invoices = [
        invoice
        for invoice in read_invoices(connection, invoice_ids)
        if invoice["status"] == "normal" and invoice["detail_status"] == "complete"
    ]
    if not invoices:
        return 0
    active = {}
    for row in allocation_dao.by_invoices(connection, [invoice["id"] for invoice in invoices]):
        if row["status"] in ("proposed", "confirmed"):
            active.setdefault(row["invoice_item_id"], []).append(row)
    task_lines = open_lines(connection)
    now, created = _now(), 0
    for invoice in invoices:
        items = [
            item
            for item in invoice["items"]
            if item["is_active"]
            and not any(row["status"] == "confirmed" for row in active.get(item["id"], []))
            and (refresh or not active.get(item["id"]))
        ]
        for group in group_plan_service.plan(connection, invoice, items, task_lines):
            group_id = str(uuid.uuid4())
            expected = []
            for row in group["rows"]:
                checks, confidence = group["checks"][row["invoice_item_id"]]
                expected.append(
                    {
                        "invoice_item_id": row["invoice_item_id"],
                        "purchase_line_id": row["purchase_line_id"],
                        "purchase_basis_id": row["purchase_basis_id"],
                        "invoice_version_id": invoice["current_version_id"],
                        "quantity": row["quantity"],
                        "amount": row["amount"],
                        "confidence": confidence,
                        "checks": {
                            "items": checks,
                            "purchaseDigest": group["lines"][row["purchase_line_id"]]["digest"],
                            "group": {"id": group_id, "orderIds": group["orderIds"]},
                        },
                    }
                )
            previous = [row for item_id in group["itemIds"] for row in active.get(item_id, [])]
            if _unchanged(previous, expected):
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
                        "review_note": "重新生成建议：整单比对结果已变化，旧待审建议由新建议替代",
                    },
                    now,
                )
            for row in expected:
                allocation_dao.insert_allocation(
                    connection,
                    {
                        "invoice_id": invoice["id"],
                        **row,
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
