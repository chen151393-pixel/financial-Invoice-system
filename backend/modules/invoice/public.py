"""invoice 模块对外门面：其他模块唯一可以导入的文件。

- 事件 InvoicesImported：发票导入事务中发布，matching 订阅后生成比对建议。
- 只读函数（需传入调用方的数据库连接，便于在同一事务中读取）：read_invoices、lock_invoice。
"""

from dataclasses import dataclass

from .policy.lemon_scope_policy import (
    describe_lemon_result,
    lemon_business_type_options,
    lemon_detail_ids,
    lemon_import_defaults,
)
from .service.invoice_reader import (
    invoice_ids_between,
    lock_invoice,
    read_invoice_accounts,
    read_invoice_amount_scope,
    read_invoices,
)
from .service.invoice_trend_reader import invoice_daily_amounts, latest_invoice_date
from .service.lemon_refresh_reader import read_lemon_refresh_targets


@dataclass(frozen=True)
class InvoicesImported:
    """本次新增的发票 ID（不含内容未变化而跳过的发票）。"""

    invoice_ids: tuple[int, ...]


__all__ = [
    "invoice_ids_between",
    "read_lemon_refresh_targets",
    "invoice_daily_amounts",
    "latest_invoice_date",
    "InvoicesImported",
    "lock_invoice",
    "read_invoices",
    "read_invoice_accounts",
    "read_invoice_amount_scope",
    "describe_lemon_result",
    "lemon_business_type_options",
    "lemon_import_defaults",
    "lemon_detail_ids",
]


@dataclass(frozen=True)
class InvoiceChanging:
    invoice_ids: tuple[int, ...]


@dataclass(frozen=True)
class InvoiceChanged:
    invoice_id: int
    previous_version_id: int
    version_id: int
    status: str


@dataclass(frozen=True)
class LemonInvoicesStored:
    """API 批次保存结果；sync 订阅并与发票版本在同一事务提交。"""

    scope: str
    request_id: str
    result: dict
