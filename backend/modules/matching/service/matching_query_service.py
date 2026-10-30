"""发票比对查询：单张发票的比对视图、待审核队列、发票列表摘要、人工分配候选。"""

from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import invoice_display_status, read_invoice_paper, read_invoices
from backend.modules.review.public import current_bases
from backend.modules.source.public import purchase_lines
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..mapper import allocation_mapper as mapper
from ..policy import allocation_policy as rules
from ..policy.anomaly_policy import anomalies
from ..policy.comparison_policy import HIGH, MEDIUM, compare, text, tier
from ..policy.confirmation_policy import evaluate
from ..policy.invoice_match_policy import match_status
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
from . import group_view_service
from .invoice_queue_service import invoice_queue
from .invoice_totals_service import InvoiceTotalsService
from .queue_scope import queue_scope

READ_ERROR = "发票比对读取失败，请检查业务数据库及迁移状态"
TIERS = {"all": (None, None), "high": (HIGH, None), "medium": (MEDIUM, HIGH), "low": (None, MEDIUM)}
# 按异常筛选需逐条计算比对项，单次最多核对的待审核建议条数
ANOMALY_SCAN = 3000


def summary_row(invoice_id, judged):
    best = judged["best_confidence"]
    return {
        "invoiceId": str(invoice_id),
        "status": judged["status"],
        "label": judged["label"],
        "tier": tier(best) if best is not None else None,
        "proposed": judged["proposed"],
        "confirmed": judged["confirmed"],
    }


def summary_rows(connection, invoice_ids, invoices):
    """按 ID 顺序给出发票的匹配状态摘要；invoices 为 read_invoices 的结果（按 ID 索引）。"""
    rows = allocation_dao.by_invoices(connection, invoice_ids)
    result = []
    for invoice_id in invoice_ids:
        invoice = invoices[invoice_id]
        judged = match_status(
            invoice_display_status(invoice),
            [row for row in rows if row["invoice_id"] == invoice_id],
            sum(item["is_active"] for item in invoice["items"]),
        )
        result.append(summary_row(invoice_id, judged))
    return result


class MatchingQueryService:
    def __init__(self, engine):
        self.engine = engine

    def order_candidates(self, query):
        from .order_candidate_service import query_candidates

        return self._read(lambda connection: query_candidates(connection, query))

    def manual_order_candidates(self, query):
        from .manual_order_service import candidates

        return self._read(lambda connection: candidates(connection, query))

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
        for key, line in lines.items():
            basis = bases.get(key)
            line.update(
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
            paper = read_invoice_paper(connection, invoice_id)
            rows = allocation_dao.by_invoices(connection, [invoice_id])
            views = self._views(connection, invoice, rows)
            items = []
            for item in invoice["items"]:
                own = [row for row in rows if row["invoice_item_id"] == item["id"]]
                confirmed = [row for row in own if row["status"] == "confirmed"]
                face = paper["items"][item["id"]]
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
                        unitPrice=text(face["unit_price"]),
                        net=mapper.paper_money(item["amount_excluding_tax"]),
                        taxRate=mapper.tax_rate(face["tax_rate"]),
                        tax=mapper.paper_money(face["tax_amount"]),
                        confirmedQuantity=text(sum((row["quantity"] for row in confirmed), Decimal(0))),
                        confirmedAmount=text(sum((row["amount"] for row in confirmed), Decimal(0))),
                        allocations=[views[row["id"]] for row in own],
                    )
                )
            normal = invoice["status"] == "normal"
            # 整单建议按当前来源重算发票行对整单合计的比对
            grouped = [row for own in group_view_service.grouped(rows).values() for row in own]
            group_lines, group_tasks = self._context(connection, grouped) if grouped else ({}, {})
            return InvoiceMatching(
                invoice=mapper.invoice_side(invoice),
                paper=mapper.invoice_paper(invoice, paper),
                groups=group_view_service.views(invoice, paper, rows, views, group_lines, group_tasks),
                items=items,
                generate=Capability(
                    allowed=normal,
                    reason="为尚无建议的发票行重新比对已审核的子采购行"
                    if normal
                    else "作废、红冲或状态未知的发票不生成建议",
                ),
            )

        return self._read(action)

    def invoice_queue(self, query):
        return self._read(
            lambda connection: invoice_queue(connection, query, self._queue_rows, _supplier_options)
        )

    def queue(self, query):
        def action(connection):
            scope = queue_scope(connection, query)
            notice = ""
            if query.anomaly == "all":
                total, rows = allocation_dao.queue(
                    connection,
                    tiers=TIERS[query.tier],
                    offset=(query.page - 1) * query.pageSize,
                    limit=query.pageSize,
                    **scope,
                )
                result = self._queue_rows(connection, rows)
                counts = allocation_dao.proposal_counts(connection, HIGH, MEDIUM, **scope)
            else:
                # 异常需逐条计算比对项：在筛选范围内逐条分类后再按分档与分页截取
                scanned, rows = allocation_dao.queue(
                    connection, tiers=TIERS["all"], offset=0, limit=ANOMALY_SCAN, **scope
                )
                wanted = query.anomaly == "abnormal"
                matched = [row for row in self._queue_rows(connection, rows) if bool(row.anomalies) == wanted]
                counts = {
                    "all": len(matched),
                    **{
                        key: sum(row.allocation.tier == key for row in matched)
                        for key in ("high", "medium", "low")
                    },
                }
                chosen = [row for row in matched if query.tier in ("all", row.allocation.tier)]
                total = len(chosen)
                start = (query.page - 1) * query.pageSize
                result = chosen[start : start + query.pageSize]
                if scanned > ANOMALY_SCAN:
                    notice = f"待审核建议超过 {ANOMALY_SCAN} 条，只在置信度最高的前 {ANOMALY_SCAN} 条中筛选；可缩小供应商或日期范围"
            pages = max(1, (total + query.pageSize - 1) // query.pageSize)
            return Queue(
                rows=result,
                total=total,
                page=query.page,
                pageSize=query.pageSize,
                pages=pages,
                counts=counts,
                suppliers=_supplier_options(connection),
                notice=notice,
            )

        return self._read(action)

    def _queue_rows(self, connection, rows):
        """按原顺序生成队列行（含当前比对项与异常分类）；同一发票的分配一起计算占用。"""
        invoices = {
            invoice["id"]: invoice
            for invoice in read_invoices(connection, [row["invoice_id"] for row in rows])
        }
        result = []
        for invoice_id in dict.fromkeys(row["invoice_id"] for row in rows):
            invoice = invoices[invoice_id]
            own = [row for row in rows if row["invoice_id"] == invoice_id]
            views = self._views(connection, invoice, allocation_dao.by_invoices(connection, [invoice_id]))
            items = {item["id"]: item for item in invoice["items"]}
            result.extend(
                QueueRow(
                    allocation=views[row["id"]],
                    invoiceId=str(invoice_id),
                    invoiceNumber=invoice["invoice_no"],
                    seller=invoice["seller_name"],
                    itemName=items[row["invoice_item_id"]]["item_name"],
                    anomalies=anomalies(views[row["id"]]),
                )
                for row in own
            )
        order = {row["id"]: index for index, row in enumerate(rows)}
        result.sort(key=lambda view: order[int(view.allocation.id)])
        return result

    def summaries(self, body):
        invoice_ids = [int(value) for value in body.invoiceIds]

        def action(connection):
            invoices = {invoice["id"]: invoice for invoice in read_invoices(connection, invoice_ids)}
            if any(invoice_id not in invoices for invoice_id in invoice_ids):
                raise ApiError(404, "发票不存在")
            return Summaries(rows=summary_rows(connection, invoice_ids, invoices))

        return self._read(action)

    def candidates(self, query):
        """人工候选保留其他订单，备注命中的子单 / 母单优先；支持订单、供应商、品名、报关单搜索。"""
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
                    line.get("parent_order_no"),
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
                        checks=mapper.check_views(checks, line.get("unit_name")),
                        confidence=text(confidence),
                        tier=tier(confidence),
                        block=rules.hard_block(invoice, line, task_line),
                    )
                )
            rows.sort(
                key=lambda row: (
                    -Decimal(row.confidence),
                    not any(check.key == "order" and check.result == "match" for check in row.checks),
                    int(row.purchase.purchaseLineId),
                )
            )
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
