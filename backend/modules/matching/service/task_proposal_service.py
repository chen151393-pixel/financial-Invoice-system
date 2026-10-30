"""任务生成后重评已有发票；订阅在 task 生成与 matching 账本更新之后执行。"""

from backend.modules.invoice.public import InvoiceQuery, read_invoice_status_scope, read_invoices
from backend.modules.source.public import purchase_lines
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..policy.order_group_policy import taken
from .group_plan_service import recall_orders
from .proposal_service import generate


def on_review_approved(connection, event):
    """复用审核事务与账本锁；分批扫描，不因分页截断漏掉历史票或跨任务整单组合。"""
    affected = [line.purchase_line_id for line in event.lines]
    if not affected:
        return
    tasks = open_lines(connection, affected)
    available = [row["purchase_line_id"] for row in tasks if not taken(row)]
    if not available:
        return  # 供应商关闭任务生成、未生成有效任务或已有收票时不触发重评
    contexts = purchase_lines(connection, available)
    before_id = None
    while batch := read_invoice_status_scope(connection, InvoiceQuery(status="normal"), before_id=before_id):
        before_id = batch[-1]["id"]
        invoices = read_invoices(connection, [row["id"] for row in batch])
        candidates = [
            invoice["id"]
            for invoice in invoices
            if invoice["detail_status"] == "complete" and recall_orders(invoice, contexts)
        ]
        # 已确认发票不在自动重评中拆出剩余行；原关联、核实历史与任务收票进度保持原样。
        confirmed = {
            row["invoice_id"]
            for row in allocation_dao.by_invoices(connection, candidates)
            if row["status"] == "confirmed"
        }
        generate(
            connection, [key for key in candidates if key not in confirmed], event.approved_by, refresh=True
        )
