"""发票列表统计：同一只读快照下汇总全部筛选范围，不依赖分页或任务缓存。"""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_invoice_amount_scope
from backend.modules.review.public import current_bases

from ..dao import allocation_dao
from ..policy.invoice_totals_policy import invoice_amounts
from ..vo.invoice_totals_vo import InvoiceTotals
from .ledger_service import effective_basis, effective_invoice


class InvoiceTotalsService:
    def __init__(self, engine):
        self.engine = engine

    def read(self, query):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        try:
            with self.engine.connect() as connection:
                # 默认业务连接为 READ COMMITTED；统计需固定快照，防止跨批换版或确认造成混算。
                if connection.dialect.name == "mysql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                with connection.begin():
                    return self._collect(connection, query.model_dump())
        except SQLAlchemyError:
            raise ApiError(503, "发票金额统计读取失败，请刷新重试") from None

    @staticmethod
    def _collect(connection, filters):
        totals, invoices = read_invoice_amount_scope(connection, filters)
        result = {
            row["currency"]: {
                **{key: row[key] for key in ("currency", "count", "gross", "tax")},
                "pendingAmount": Decimal(0),
                "pendingCount": 0,
                "reviewAmount": Decimal(0),
                "reviewCount": 0,
            }
            for row in totals
        }
        while invoices:
            accumulate(connection, invoices, result)
            _, invoices = read_invoice_amount_scope(connection, filters, after_id=invoices[-1]["id"])
        for row in result.values():
            for key in ("gross", "tax", "pendingAmount", "reviewAmount"):
                row[key] = format(row[key], "f") if row[key] is not None else None
        return InvoiceTotals(amounts=list(result.values()))


def accumulate(connection, invoices, result):
    rows = allocation_dao.confirmed_for_totals(connection, [head["id"] for head in invoices])
    bases = current_bases(connection, sorted({row["purchase_line_id"] for row in rows})) if rows else {}
    grouped = defaultdict(list)
    for row in rows:
        # 有效版本取复核历史的最后承接记录，与现有账本保持一致。
        grouped[row["invoice_id"]].append(
            {
                **row,
                "effective_invoice": effective_invoice(row),
                "effective_basis": effective_basis(row),
            }
        )
    for invoice in invoices:
        pending, review = invoice_amounts(invoice, grouped[invoice["id"]], bases)
        total = result[invoice["currency"]]
        total["pendingAmount"] += pending
        total["pendingCount"] += int(pending > 0)
        total["reviewAmount"] += review
        total["reviewCount"] += int(review > 0)
