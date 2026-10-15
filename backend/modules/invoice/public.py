"""invoice 模块对外门面：其他模块唯一可以导入的文件。

- 事件 InvoicesImported：发票导入事务中发布，matching 订阅后生成比对建议。
- 只读函数（需传入调用方的数据库连接，便于在同一事务中读取）：read_invoices、lock_invoice。
"""

from dataclasses import dataclass

from .service.invoice_reader import lock_invoice, read_invoices


@dataclass(frozen=True)
class InvoicesImported:
    """本次新增的发票 ID（不含内容未变化而跳过的发票）。"""

    invoice_ids: tuple[int, ...]


__all__ = ["InvoicesImported", "lock_invoice", "read_invoices"]
