"""review 模块对外门面：其他模块唯一可以导入的文件。"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ApprovedLine:
    """审核冻结的一条子采购行（开票口径），task 模块据此生成任务行。"""

    review_line_id: int
    purchase_order_id: int
    purchase_line_id: int
    supplier_id: int | None
    company_id: int | None
    order_no: str
    currency: str | None
    quantity: Decimal | None
    unit: str | None
    amount: Decimal | None


@dataclass(frozen=True)
class ReviewApproved:
    """财务审核通过（在审核事务中发布）。superseded_review_id 为被本次替代的上一条有效审核。"""

    review_id: int
    superseded_review_id: int | None
    ns_account: str
    customs_declaration_id: int
    record_no: str | None
    revision: int
    approved_by: str
    lines: tuple[ApprovedLine, ...]


__all__ = ["ApprovedLine", "ReviewApproved"]
