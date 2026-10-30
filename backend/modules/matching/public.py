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
class ClosedLine:
    purchase_line_id: int
    purchase_basis_id: int
    # 由整单组 ID 与子采购行派生，重复提交不重复结束
    request_id: str


@dataclass(frozen=True)
class LinesClosedByDifference:
    """整单关联确认时发票少于子采购单：这些子采购明细按差异结束（在比对事务中发布，task 同事务处理）。"""

    lines: tuple[ClosedLine, ...]
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
    "ClosedLine",
    "LineReceipt",
    "LinesClosedByDifference",
    "InvoiceMatchingChanged",
    "read_writeback_snapshot",
    "writeback_invoice_ids",
]
