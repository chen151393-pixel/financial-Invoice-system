"""整单建议视图与整组审核：按 checks.group 归组，按当前来源实时重算发票行对整单合计的比对。"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_invoice_paper, read_invoices
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..dto.matching_dto import ConfirmBody
from ..mapper import allocation_mapper as mapper
from ..policy import allocation_policy as rules
from ..policy.comparison_policy import HIGH, text, tier
from ..policy.group_comparison_policy import compare_group
from ..policy.order_group_policy import ONE_INVOICE, order_share, short_lines, taken
from ..public import ClosedLine, LinesClosedByDifference
from ..vo.matching_vo import Capability, GroupItem, GroupLine, GroupOrder, GroupView
from . import approval_service

SHORT_REASON = "发票少于子采购单，差额按差异结束"


def group_id(row):
    return ((row["checks"] or {}).get("group") or {}).get("id")


def grouped(rows):
    """{组 ID: [待审核分配]}，组内按 ID 排序。"""
    result = {}
    for row in sorted(rows, key=lambda value: value["id"]):
        if row["status"] == "proposed" and group_id(row):
            result.setdefault(group_id(row), []).append(row)
    return result


def evaluate(invoice, paper, rows, lines):
    """返回 ({发票行 ID: (checks, confidence, parts)}, 需说明原因, 阻断原因)。"""
    items = {item["id"]: item for item in invoice["items"]}
    result, reasons, block = {}, [], ""
    for item_id in dict.fromkeys(row["invoice_item_id"] for row in rows):
        own = [row for row in rows if row["invoice_item_id"] == item_id]
        if any(lines.get(row["purchase_line_id"]) is None for row in own):
            block = block or "子采购行已停用或不存在，请驳回后重新生成建议"
            continue
        # 比对口径为子采购整单应开（历史分配没有快照时取分配本身）
        parts = [(lines[row["purchase_line_id"]], *order_share(row)) for row in own]
        tax = (paper["items"].get(item_id) or {}).get("tax_amount")
        checks, confidence = compare_group(invoice, items[item_id], tax, parts)
        result[item_id] = (checks, confidence, own)
        reasons += rules.note_reasons(checks, False, False)
    return result, list(dict.fromkeys(reasons)), block


def views(invoice, paper, rows, row_views, lines, tasks=None):
    """tasks 为 {子采购行 ID: 任务行}，用于提示子采购单已由其他发票开具。"""
    tasks = tasks or {}
    result = []
    for key, own in grouped(rows).items():
        compared, reasons, block = evaluate(invoice, paper, own, lines)
        if not block and any(
            taken(tasks[row["purchase_line_id"]]) for row in own if row["purchase_line_id"] in tasks
        ):
            block = ONE_INVOICE
        if short_lines(own):
            reasons = list(dict.fromkeys([*reasons, SHORT_REASON]))
        # 组内每条分配的不可绕过条件（来源变化、容量、版本等）沿用逐条判断。
        block = block or next(
            (row_views[row["id"]].confirm.reason for row in own if not row_views[row["id"]].confirm.allowed),
            "",
        )
        orders = {}
        for row in own:
            line = lines.get(row["purchase_line_id"]) or {}
            order = orders.setdefault(
                str(line.get("purchase_order_id", "")),
                {
                    "purchaseOrderId": str(line.get("purchase_order_id", "")),
                    "orderNo": line.get("order_no") or "",
                    "parentOrderNo": line.get("parent_order_no") or "",
                    "supplier": line.get("supplier_name") or "",
                    "company": line.get("company_name") or "",
                    "lineCount": 0,
                },
            )
            order["lineCount"] += 1
        items = []
        for item_id, (checks, confidence, parts) in compared.items():
            items.append(
                GroupItem(
                    invoiceItemId=str(item_id),
                    checks=mapper.check_views(checks),
                    confidence=text(confidence),
                    tier=tier(confidence),
                    quantity=text(sum((row["quantity"] for row in parts), Decimal(0))),
                    amount=text(sum((row["amount"] for row in parts), Decimal(0))),
                    lines=[
                        GroupLine(
                            purchaseLineId=str(row["purchase_line_id"]),
                            orderNo=lines[row["purchase_line_id"]]["order_no"] or "",
                            item=lines[row["purchase_line_id"]]["item_name"]
                            or lines[row["purchase_line_id"]]["declaration_name"]
                            or "",
                            specification=lines[row["purchase_line_id"]]["specification"] or "",
                            unit=lines[row["purchase_line_id"]]["unit_name"] or "",
                            quantity=text(row["quantity"]),
                            amount=text(row["amount"]),
                            taxRate=mapper.tax_rate(lines[row["purchase_line_id"]]["tax_rate"]),
                        )
                        for row in parts
                    ],
                )
            )
        lowest = min((confidence for _, confidence, _ in compared.values()), default=Decimal(0))
        result.append(
            GroupView(
                id=key,
                orders=[GroupOrder(**order) for order in orders.values()],
                items=items,
                confidence=text(lowest),
                tier=tier(lowest),
                noteReasons=reasons,
                confirm=Capability(
                    allowed=not block,
                    reason=block
                    or ("通过时需填写说明" if reasons else "整组通过：全部子采购明细一次记入收票进度"),
                ),
                reject=Capability(allowed=True, reason="整组驳回后可重新生成建议或人工处理"),
                allocationIds=[str(row["id"]) for row in own],
            )
        )
    return result


def _rows(connection, invoice_id, key):
    rows = [row for row in allocation_dao.by_invoices(connection, [invoice_id]) if group_id(row) == key]
    if not rows:
        raise ApiError(404, "整单建议不存在或不属于该发票")
    return sorted(rows, key=lambda row: row["id"])


def approve_rows(service, connection, rows, body, actor):
    """在调用方事务内整组逐条通过；需说明而未填写或任一条不能通过时抛错，由事务整体回滚。"""
    invoice_id = int(body.invoiceId)
    invoice = read_invoices(connection, [invoice_id])[0]
    lines, _ = service.queries._context(connection, rows)
    _, reasons, block = evaluate(invoice, read_invoice_paper(connection, invoice_id), rows, lines)
    if block:
        raise ApiError(409, block)
    tasks = open_lines(connection, sorted({row["purchase_line_id"] for row in rows}))
    if any(taken(task) for task in tasks):
        raise ApiError(409, ONE_INVOICE)
    short = short_lines(rows)
    reasons = list(dict.fromkeys([*reasons, *([SHORT_REASON] if short else [])]))
    note = body.note.strip()
    if reasons and not note:
        raise ApiError(400, "请填写审核说明：" + "、".join(reasons))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in rows:
        confirm_body = ConfirmBody(
            note=note,
            invoiceVersionId=body.invoiceVersionId,
            purchaseBasisId=str(row["purchase_basis_id"]) if row["purchase_basis_id"] else None,
        )
        approval_service.approve(
            service,
            connection,
            allocation_dao.get(connection, row["id"]),
            confirm_body,
            actor,
            now,
            grouped=True,
        )
    if short:
        # 一张子采购单只由一张发票开具：发票少的明细在同一事务内按差异结束，不再等待其他发票。
        service.events.publish(
            connection,
            LinesClosedByDifference(
                tuple(
                    ClosedLine(
                        row["purchase_line_id"],
                        row["purchase_basis_id"],
                        str(
                            uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"matching-close:{group_id(row)}:{row['purchase_line_id']}",
                            )
                        ),
                    )
                    for row in short
                ),
                actor,
                note,
            ),
        )


def confirm(service, key, body, actor, *, batch=False):
    """整组通过：同一账本事务内逐条通过，任一条失败全部回滚。"""

    def action(connection):
        invoice_id = int(body.invoiceId)
        rows = _rows(connection, invoice_id, key)
        if all(row["status"] == "confirmed" and row["reviewed_by"] == actor for row in rows):
            return invoice_id  # 同一操作重复提交，返回原结果
        if any(row["status"] != "proposed" for row in rows):
            raise ApiError(409, "整单建议已部分处理或失效，请刷新后核对")
        if batch and any(row["confidence"] is None or row["confidence"] < HIGH for row in rows):
            raise ApiError(409, "整单建议置信度未达到高档，请在详情页审核")
        approve_rows(service, connection, rows, body, actor)
        return invoice_id

    return service._run(action, actor)


def reject(service, key, body, actor):
    def action(connection):
        invoice_id = int(body.invoiceId)
        rows = _rows(connection, invoice_id, key)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for row in rows:
            if row["status"] == "proposed":
                allocation_dao.update_status(
                    connection,
                    row["id"],
                    {
                        "status": "rejected",
                        "reviewed_by": actor,
                        "reviewed_at": now,
                        "review_note": body.note.strip() or None,
                    },
                    now,
                )
        return invoice_id

    return service._run(action, actor)


class GroupBatch:
    """批量通过时把属于整单建议的记录按组归并；组外记录仍逐条处理。"""

    def __init__(self, engine, ids):
        self.items, self.ids = [], set()
        with engine.connect() as connection:
            found = {}
            for value in dict.fromkeys(int(raw) for raw in ids):
                row = allocation_dao.get(connection, value)
                key = group_id(row) if row is not None and row["status"] == "proposed" else None
                if key:
                    found.setdefault((key, row["invoice_id"]), set())
            for key, invoice_id in found:
                members = _rows(connection, invoice_id, key)
                own = [str(row["id"]) for row in members]
                self.items.append((key, invoice_id, own))
                self.ids.update(own)

    @staticmethod
    def body(invoice_id):
        from ..dto.matching_dto import GroupConfirmBody

        return GroupConfirmBody(invoiceId=str(invoice_id))
