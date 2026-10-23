"""发票比对查询：单张发票的比对视图、待审核队列、发票列表摘要、人工分配候选。"""

from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import invoice_ids_between, read_invoices
from backend.modules.review.public import current_bases
from backend.modules.source.public import purchase_lines, supplier_line_ids, unit_label, unit_names
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..mapper import allocation_mapper as mapper
from ..policy import allocation_policy as rules
from ..policy.comparison_policy import HIGH, MEDIUM, compare, text, tier
from ..policy.confirmation_policy import evaluate
from ..vo.matching_vo import (
    Candidate,
    Candidates,
    Capability,
    InvoiceMatching,
    ItemView,
    Queue,
    QueueRow,
    Summaries,
    SupplierOption,
)
from .invoice_totals_service import InvoiceTotalsService

READ_ERROR = "发票比对读取失败，请检查业务数据库及迁移状态"
TIERS = {"all": (None, None), "high": (HIGH, None), "medium": (MEDIUM, HIGH), "low": (None, MEDIUM)}


class MatchingQueryService:
    def __init__(self, engine):
        self.engine = engine

    def invoice_totals(self, query):
        return InvoiceTotalsService(self.engine).read(query)

    def _read(self, action):
        try:
            with self.engine.connect() as connection:
                return action(connection)
        except SQLAlchemyError:
            raise ApiError(503, READ_ERROR) from None

    @staticmethod
    def _context(connection, rows):
        line_ids = sorted({row["purchase_line_id"] for row in rows})
        tasks = (
            {line["purchase_line_id"]: line for line in open_lines(connection, line_ids)} if line_ids else {}
        )
        lines = purchase_lines(connection, line_ids)
        bases = current_bases(connection, line_ids)
        units = unit_names(connection)
        for key, line in lines.items():
            basis = bases.get(key)
            line.update(
                unit_display=unit_label(line["unit"], units),
                currency=basis["currency"] if basis else None,
                basis_reason=basis["reason"] if basis else "缺少有效开票依据",
                basis_id=basis["id"] if basis else None,
                currency_issue="已按人工证据核实"
                if basis and basis["currency_source"] == "manual_verified"
                else line["currency_issue"],
            )
        return lines, tasks

    def _views(self, connection, invoice, rows):
        lines, tasks = self._context(connection, rows)
        items = {item["id"]: item for item in invoice["items"]}
        result = {}
        for row in rows:
            confirmed = [
                other
                for other in rows
                if other["invoice_item_id"] == row["invoice_item_id"]
                and other["status"] == "confirmed"
                and other["id"] != row["id"]
            ]
            used = (
                sum((other["quantity"] for other in confirmed), Decimal(0)),
                sum((other["amount"] for other in confirmed), Decimal(0)),
            )
            line, task_line = lines.get(row["purchase_line_id"]), tasks.get(row["purchase_line_id"])
            checks, capabilities, reasons = evaluate(
                row, invoice, items[row["invoice_item_id"]], line, task_line, used
            )
            purchase = mapper.purchase_side(row["purchase_line_id"], line, task_line)
            result[row["id"]] = mapper.allocation_view(
                {**row, "current_invoice_version_id": invoice["current_version_id"]},
                checks,
                purchase,
                capabilities,
                reasons,
            )
        return result

    def invoice(self, invoice_id):
        def action(connection):
            found = read_invoices(connection, [invoice_id])
            if not found:
                raise ApiError(404, "发票不存在")
            invoice = found[0]
            rows = allocation_dao.by_invoices(connection, [invoice_id])
            views = self._views(connection, invoice, rows)
            items = []
            for item in invoice["items"]:
                own = [row for row in rows if row["invoice_item_id"] == item["id"]]
                confirmed = [row for row in own if row["status"] == "confirmed"]
                items.append(
                    ItemView(
                        active=item["is_active"],
                        id=str(item["id"]),
                        lineNo=item["line_no"],
                        item=item["item_name"],
                        specification=item["specification"],
                        unit=item["unit"],
                        quantity=text(item["quantity"]),
                        amount=text(item["amount_including_tax"]),
                        confirmedQuantity=text(sum((row["quantity"] for row in confirmed), Decimal(0))),
                        confirmedAmount=text(sum((row["amount"] for row in confirmed), Decimal(0))),
                        allocations=[views[row["id"]] for row in own],
                    )
                )
            normal = invoice["status"] == "normal"
            return InvoiceMatching(
                invoice=mapper.invoice_side(invoice),
                items=items,
                generate=Capability(
                    allowed=normal,
                    reason="为尚无建议的发票行重新比对已审核的子采购行"
                    if normal
                    else "作废、红冲或状态未知的发票不生成建议",
                ),
            )

        return self._read(action)

    def queue(self, query):
        def action(connection):
            scope = {
                "line_ids": set(supplier_line_ids(connection, int(query.supplierId)))
                if query.supplierId
                else None,
                "invoice_ids": set(invoice_ids_between(connection, query.invoiceFrom, query.invoiceTo))
                if query.invoiceFrom
                else None,
            }
            total, rows = allocation_dao.queue(
                connection,
                tiers=TIERS[query.tier],
                offset=(query.page - 1) * query.pageSize,
                limit=query.pageSize,
                **scope,
            )
            invoices = {
                invoice["id"]: invoice
                for invoice in read_invoices(connection, [row["invoice_id"] for row in rows])
            }
            result = []
            for invoice_id in dict.fromkeys(row["invoice_id"] for row in rows):
                invoice = invoices[invoice_id]
                own = [row for row in rows if row["invoice_id"] == invoice_id]
                all_rows = allocation_dao.by_invoices(connection, [invoice_id])
                views = self._views(connection, invoice, all_rows)
                items = {item["id"]: item for item in invoice["items"]}
                result.extend(
                    QueueRow(
                        allocation=views[row["id"]],
                        invoiceId=str(invoice_id),
                        invoiceNumber=invoice["invoice_no"],
                        seller=invoice["seller_name"],
                        itemName=items[row["invoice_item_id"]]["item_name"],
                    )
                    for row in own
                )
            order = {row["id"]: index for index, row in enumerate(rows)}
            result.sort(key=lambda view: order[int(view.allocation.id)])
            counts = allocation_dao.proposal_counts(connection, HIGH, MEDIUM, **scope)
            pages = max(1, (total + query.pageSize - 1) // query.pageSize)
            return Queue(
                rows=result,
                total=total,
                page=query.page,
                pageSize=query.pageSize,
                pages=pages,
                counts=counts,
                suppliers=_supplier_options(connection),
            )

        return self._read(action)

    def summaries(self, body):
        invoice_ids = [int(value) for value in body.invoiceIds]

        def action(connection):
            invoices = {invoice["id"]: invoice for invoice in read_invoices(connection, invoice_ids)}
            rows = allocation_dao.by_invoices(connection, invoice_ids)
            result = []
            for invoice_id in invoice_ids:
                if invoice_id not in invoices:
                    raise ApiError(404, "发票不存在")
                own = [row for row in rows if row["invoice_id"] == invoice_id]
                proposed = [row for row in own if row["status"] == "proposed"]
                confirmed_items = {
                    row["invoice_item_id"]
                    for row in own
                    if row["status"] == "confirmed" and row["verification_status"] == "valid"
                }
                item_count = sum(item["is_active"] for item in invoices[invoice_id]["items"])
                if any(row["status"] == "confirmed" and row["verification_status"] != "valid" for row in own):
                    status, label = "needs_review", "待复核占用"
                elif confirmed_items and len(confirmed_items) >= item_count:
                    status, label = "confirmed", "已比对"
                elif confirmed_items:
                    status, label = "partial", "部分比对"
                elif proposed:
                    status, label = "proposed", "待审核建议"
                else:
                    status, label = "none", "未比对"
                best = max(
                    (row["confidence"] for row in proposed if row["confidence"] is not None), default=None
                )
                result.append(
                    {
                        "invoiceId": str(invoice_id),
                        "status": status,
                        "label": label,
                        "tier": tier(best) if best is not None else None,
                        "proposed": len(proposed),
                        "confirmed": len(confirmed_items),
                    }
                )
            return Summaries(rows=result)

        return self._read(action)

    def candidates(self, query):
        """人工分配候选：全部未结束的有效任务行，按关键字（子采购单号、供应商、品名、报关单号）筛选。"""
        invoice_id, item_id, keyword = (
            int(query.invoiceId),
            int(query.invoiceItemId),
            query.keyword.strip().lower(),
        )

        def action(connection):
            found = read_invoices(connection, [invoice_id])
            item = next((row for row in found[0]["items"] if row["id"] == item_id), None) if found else None
            if item is None:
                raise ApiError(404, "发票行不存在或不属于该发票")
            invoice = found[0]
            task_lines = self._candidate_tasks(connection, invoice_id)
            lines, _ = self._context(connection, task_lines)
            rows = []
            for task_line in task_lines:
                line = lines.get(task_line["purchase_line_id"])
                if line is None:
                    continue
                fields = (
                    line["order_no"],
                    line["supplier_name"],
                    line["declaration_name"],
                    line["item_name"],
                    task_line["record_no"],
                )
                if keyword and not any(keyword in (value or "").lower() for value in fields):
                    continue
                checks, confidence = compare(invoice, item, line, *rules.remaining(task_line))
                rows.append(
                    Candidate(
                        purchase=mapper.purchase_side(task_line["purchase_line_id"], line, task_line),
                        checks=mapper.check_views(checks, line.get("unit_display")),
                        confidence=text(confidence),
                        tier=tier(confidence),
                        block=rules.hard_block(invoice, line, task_line),
                    )
                )
            rows.sort(key=lambda row: (-Decimal(row.confidence), int(row.purchase.purchaseLineId)))
            return Candidates(rows=rows[:50], total=len(rows))

        return self._read(action)

    @staticmethod
    def _candidate_tasks(connection, invoice_id):
        # 同票原占用所在行即使已经收齐，也必须能选择原子替换。
        existing_ids = sorted(
            {
                row["purchase_line_id"]
                for row in allocation_dao.by_invoices(connection, [invoice_id])
                if row["status"] == "confirmed"
            }
        )
        rows = open_lines(connection) + open_lines(connection, existing_ids)
        return list({row["purchase_line_id"]: row for row in rows}.values())


def _supplier_options(connection):
    """待审核建议涉及的供应商（按子采购单供应商），供队列筛选下拉使用。"""
    contexts = purchase_lines(connection, allocation_dao.proposed_line_ids(connection))
    found = {
        context["supplier_id"]: context["supplier_name"] or f"供应商 {context['supplier_id']}"
        for context in contexts.values()
        if context["supplier_id"]
    }
    return [
        SupplierOption(id=str(key), name=name)
        for key, name in sorted(found.items(), key=lambda item: (item[1], item[0]))
    ]
