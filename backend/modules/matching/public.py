"""matching 模块对外门面：其他模块唯一可以导入的文件（事件契约）。"""

from dataclasses import dataclass
from decimal import Decimal

from .service.writeback_reader import read_writeback_snapshot, writeback_invoice_ids


@dataclass(frozen=True)
class LineReceipt:
    """一条子采购行全部已通过分配的合计；closed 为人工确认该行已开完（含差异）。"""

    purchase_line_id: int
    quantity: Decimal
    amount: Decimal
    closed: bool = False
    purchase_basis_id: int | None = None
    ledger_sha256: str = ""
    requires_review: bool = False
    pending_quantity: Decimal = Decimal(0)
    pending_amount: Decimal = Decimal(0)


@dataclass(frozen=True)
class AllocationChanged:
    """分配通过或取消后发布（在比对事务中）；task 订阅后重算任务行已收与任务状态。"""

    receipts: tuple[LineReceipt, ...]
    actor: str
    reason: str


@dataclass(frozen=True)
class InvoiceMatchingChanged:
    """完整用例末尾发布；订阅方在同一事务冻结审核快照，不调用 NS。"""

    invoice_ids: tuple[int, ...]
    actor: str
    reason: str


__all__ = [
    "AllocationChanged",
    "LineReceipt",
    "InvoiceMatchingChanged",
    "read_writeback_snapshot",
    "writeback_invoice_ids",
]
