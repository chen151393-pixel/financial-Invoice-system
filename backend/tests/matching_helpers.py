"""发票比对测试辅助：整单建议整组通过、部分开票人工关联。"""

from uuid import uuid4

from backend.modules.matching.dto.matching_dto import GroupConfirmBody, ManualBody


def confirm_groups(world, invoice_id, actor, note=""):
    """整组通过该发票全部待审核整单建议，返回最后的比对视图。"""
    view = world["queries"].invoice(invoice_id)
    for group in view.groups:
        view = world["allocations"].confirm_group(
            group.id, GroupConfirmBody(invoiceId=str(invoice_id), note=note), actor
        )
    return view


def manual_allocation(world, invoice_id, item_id, purchase_line_id, quantity, amount, actor, note="人工核对"):
    """部分开票不自动建议：按发票行与子采购行人工关联（直接通过）。"""
    body = ManualBody(
        requestId=uuid4(),
        invoiceId=str(invoice_id),
        invoiceItemId=str(item_id),
        purchaseLineId=str(purchase_line_id),
        quantity=str(quantity),
        amount=str(amount),
        note=note,
    )
    return world["allocations"].create_manual(body, actor)
