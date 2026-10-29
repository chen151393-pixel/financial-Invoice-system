"""invoice 模块对外门面：其他模块唯一可以导入的文件。

- 事件 InvoicesImported：发票导入事务中发布，matching 订阅后生成比对建议。
- 只读函数（需传入调用方的数据库连接，便于在同一事务中读取）：read_invoices、lock_invoice、invoices_by_number、
  read_invoice_paper（比对详情页票面展示字段）、
  read_invoice_status_scope / read_invoice_page（按列表条件分批读取状态、在给定发票范围内分页）。
- InvoiceQuery / InvoiceList：列表查询条件与分页结果结构，供按匹配状态筛选的列表复用。
"""

from dataclasses import dataclass

from .dto.invoice_dto import InvoiceQuery
from .policy.lemon_scope_policy import (
    describe_lemon_result,
    lemon_business_type_options,
    lemon_detail_ids,
    lemon_import_defaults,
)
from .service.invoice_reader import (
    invoice_display_status,
    invoice_ids_between,
    invoices_by_number,
    lock_invoice,
    read_invoice_accounts,
    read_invoice_amount_scope,
    read_invoice_page,
    read_invoice_paper,
    read_invoice_status_scope,
    read_invoices,
    read_receipt_dates,
)
from .service.lemon_refresh_reader import read_lemon_refresh_targets
from .vo.invoice_vo import InvoiceList


@dataclass(frozen=True)
class InvoicesImported:
    """本次新增的发票 ID（不含内容未变化而跳过的发票）。"""

    invoice_ids: tuple[int, ...]


__all__ = [
    "invoice_ids_between",
    "read_lemon_refresh_targets",
    "InvoicesImported",
    "lock_invoice",
    "invoices_by_number",
    "read_invoices",
    "read_receipt_dates",
    "read_invoice_accounts",
    "read_invoice_amount_scope",
    "read_invoice_page",
    "read_invoice_paper",
    "read_invoice_status_scope",
    "invoice_display_status",
    "InvoiceQuery",
    "InvoiceList",
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
