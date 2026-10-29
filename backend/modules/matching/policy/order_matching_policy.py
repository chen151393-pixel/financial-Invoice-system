"""整单分配规划：原始发票行不拆改，按采购剩余应开生成分配且严格守恒。"""

from decimal import Decimal, localcontext

from .allocation_policy import hard_block, remaining
from .comparison_policy import item_name


def plan(invoice, lines, tasks, bases, conversion):
    """返回 (分配计划, 阻断原因)。多发票行只接受品名唯一对应，不猜测同名行之间的分摊。"""
    items = [item for item in invoice["items"] if item["is_active"]]
    if not items:
        return [], "发票没有有效明细"
    result = []
    for line_id, line in sorted(lines.items()):
        task, basis = tasks.get(line_id), bases.get(line_id)
        block = hard_block(invoice, line, task)
        if block:
            return [], block
        if basis is None or not basis["allowed"] or task["purchase_basis_id"] != basis["id"]:
            return [], "开票依据已变化或未审核，请先重新审核任务"
        if task.get("closed_with_difference"):
            return [], "子采购单含已按差异结束的明细，请逐行核实"
        quantity, amount = remaining(task)
        if quantity is None or amount is None or quantity < 0 or amount < 0:
            return [], "子采购单剩余数量或金额缺失、超开，请逐行核实"
        if quantity == 0 and amount == 0:
            continue
        if quantity <= 0 or amount <= 0:
            return [], "子采购单有数量与金额进度不一致的明细，请逐行核实"
        matches = [
            item
            for item in items
            if item_name(item["item_name"]) == item_name(line["declaration_name"] or line["item_name"])
        ]
        if len(matches) != 1:
            return [], "发票品名无法唯一对应采购明细，请使用逐行分配核实"
        item = matches[0]
        if not item["unit"] or not basis["unit"]:
            return [], "发票或采购明细缺少单位，须先补齐"
        if item["unit"] == basis["unit"] and (
            conversion.conversionNumerator != 1 or conversion.conversionDenominator != 1
        ):
            return [], "同单位必须使用 1 / 1 换算"
        with localcontext() as context:
            context.prec = 64
            invoice_quantity = quantity * conversion.conversionDenominator / conversion.conversionNumerator
            if invoice_quantity != invoice_quantity.quantize(Decimal("0.00000001")):
                return [], "换算后发票分配数量超过 8 位小数，不能舍入分配"
        result.append(
            {
                "invoice_item_id": item["id"],
                "purchase_line_id": line_id,
                "purchase_basis_id": basis["id"],
                "quantity": invoice_quantity,
                "purchase_quantity": quantity,
                "amount": amount,
            }
        )
    for item in items:
        parts = [part for part in result if part["invoice_item_id"] == item["id"]]
        if (
            not parts
            or sum((part["quantity"] for part in parts), Decimal(0)) != item["quantity"]
            or sum((part["amount"] for part in parts), Decimal(0)) != item["amount_including_tax"]
        ):
            return [], "发票数量或价税合计与整单剩余应开不一致，不能整单分配"
    return result, ""
