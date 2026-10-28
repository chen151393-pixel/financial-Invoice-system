"""提供整票审核快照；不在任务模块复写匹配完整性规则。"""

from backend.modules.invoice.public import read_invoices
from backend.modules.review.public import current_bases
from backend.modules.source.public import writeback_context

from ..dao import allocation_dao
from ..policy.writeback_readiness import assess


def read_writeback_snapshot(connection, invoice_id):
    invoices = read_invoices(connection, [invoice_id])
    rows = allocation_dao.by_invoices(connection, [invoice_id])
    line_ids = sorted({row["purchase_line_id"] for row in rows if row["status"] == "confirmed"})
    return assess(
        invoices[0] if invoices else None,
        rows,
        current_bases(connection, line_ids),
        writeback_context(connection, line_ids),
    )


def writeback_invoice_ids(connection, after_id=0, limit=25):
    return allocation_dao.confirmed_invoice_ids(connection, after_id, limit)
