"""确认/复核分配：锁定两端版本、校验容量与换算、追加不可变核实历史。"""

from backend.core.errors import ApiError
from backend.modules.invoice.public import lock_invoice, read_invoices
from backend.modules.review.public import current_bases
from backend.modules.source.public import purchase_lines, unit_names
from backend.modules.task.public import open_lines

from ..dao import allocation_dao, ledger_dao
from ..policy import allocation_policy as rules
from ..policy.comparison_policy import compare
from ..policy.conversion_policy import convert
from . import ledger_service


def context(connection, allocation):
    """锁定并读取审核所需的全部上下文。"""
    purchase_line_id, invoice_id = allocation["purchase_line_id"], allocation["invoice_id"]
    basis = current_bases(connection, [purchase_line_id], lock=True).get(purchase_line_id)
    task_lines = open_lines(connection, [purchase_line_id], lock=True)
    lock_invoice(connection, invoice_id)
    found = read_invoices(connection, [invoice_id])
    item = (
        next((row for row in found[0]["items"] if row["id"] == allocation["invoice_item_id"]), None)
        if found
        else None
    )
    if item is None:
        raise ApiError(404, "发票行不存在或不属于该发票")
    invoice = found[0]
    line = purchase_lines(connection, [purchase_line_id]).get(purchase_line_id)
    if line is not None:
        line = {
            **line,
            "currency": basis["currency"] if basis else None,
            "basis_reason": basis["reason"] if basis else "缺少有效开票依据",
        }
    allocation_dao.get(connection, allocation["id"], lock=True)
    return invoice, item, line, task_lines[0] if task_lines else None, basis


def approve(service, connection, allocation, body, actor, now, *, reverify=False):
    invoice, item, line, task_line, basis = context(connection, allocation)
    note = body.note.strip()
    _validate(connection, allocation, body, invoice, item, line, task_line, basis, reverify)
    converted = convert(allocation["quantity"], item, basis, body, unit_names(connection))
    if reverify and allocation["verification_status"] == "valid":
        previous = (allocation["verification_history"] or [{}])[-1]
        if (
            previous.get("action") == "reverified"
            and previous.get("actor") == actor
            and previous.get("note") == note
            and previous.get("purchaseBasisId") == basis["id"]
            and previous.get("invoiceVersionId") == invoice["current_version_id"]
            and all(allocation[key] == value for key, value in converted.items())
        ):
            return
        raise ApiError(409, "当前分配已核实；如需更改请使用替换分配")
    compared_item = {
        **item,
        "quantity": converted["purchase_quantity"],
        "amount_including_tax": allocation["amount"],
        # 部分分配时按含税比例折算不含税金额，供申报价校验
        "amount_excluding_tax": item["amount_excluding_tax"]
        * allocation["amount"]
        / item["amount_including_tax"]
        if item.get("amount_excluding_tax") is not None and item["amount_including_tax"]
        else item.get("amount_excluding_tax"),
    }
    checks, _ = compare(invoice, compared_item, line, *rules.remaining(task_line))
    exceeds = rules.exceeds_expected(task_line, converted["purchase_quantity"], allocation["amount"])
    reasons = rules.note_reasons(checks, exceeds, False)
    if (reasons or reverify) and not note:
        raise ApiError(400, "请填写审核说明：" + "、".join(reasons or ["重新核实版本"]))
    history_row = {**allocation, **converted, "review_note": note, "verification_issues": []}
    history = (allocation["verification_history"] or []) + [
        ledger_service.history_entry(
            history_row,
            "reverified" if reverify else "confirmed",
            actor,
            basis["id"],
            invoice["current_version_id"],
            now,
        )
    ]
    values = {
        **converted,
        "status": "confirmed",
        "exceeds_expected": exceeds,
        "closes_purchase_line": False,
        "verification_status": "valid",
        "verification_issues": [],
        "verification_history": history,
    }
    if not reverify:
        values.update(
            invoice_version_id=invoice["current_version_id"],
            purchase_basis_id=basis["id"],
            reviewed_by=actor,
            reviewed_at=now,
            review_note=note or None,
        )
    allocation_dao.update_status(connection, allocation["id"], values, now)
    service._publish(
        connection, allocation["purchase_line_id"], actor, f"发票 {invoice['invoice_no']} 比对通过"
    )


def _validate(connection, allocation, body, invoice, item, line, task_line, basis, reverify):
    block = rules.hard_block(invoice, line, task_line)
    if not block and not item["is_active"]:
        block = "发票逻辑明细已停用，须核实或取消原分配"
    if not block and body.closesPurchaseLine:
        block = "按差异结束已移到任务行，请确认分配后在任务详情操作"
    if (
        not block
        and not reverify
        and allocation["checks"]
        and line["digest"] != allocation["checks"].get("purchaseDigest")
    ):
        block = "子采购行内容在建议生成后已变化，比对依据过期，请重新生成建议"
    if (
        not block
        and not reverify
        and allocation["invoice_version_id"]
        and allocation["invoice_version_id"] != invoice["current_version_id"]
    ):
        block = "发票版本已变化，请重新生成建议"
    if (
        not block
        and not reverify
        and allocation["purchase_basis_id"]
        and allocation["purchase_basis_id"] != basis["id"]
    ):
        block = "开票依据已变化，请重新生成建议"
    if not block and (
        (body.invoiceVersionId and int(body.invoiceVersionId) != invoice["current_version_id"])
        or (body.purchaseBasisId and int(body.purchaseBasisId) != basis["id"])
    ):
        block = "页面版本已过期，请刷新后重新核实"
    if (
        not block
        and not reverify
        and ledger_dao.unresolved(connection, invoice["id"], allocation["purchase_line_id"], allocation["id"])
    ):
        block = "相关发票或子采购仍有待复核占用，请先处理原分配"
    if not block:
        used = allocation_dao.confirmed_by_item(connection, item["id"], exclude_id=allocation["id"])
        block = rules.capacity_block(item, *used, allocation["quantity"], allocation["amount"])
    if block:
        raise ApiError(409, block)
