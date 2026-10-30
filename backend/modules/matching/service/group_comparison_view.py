"""待审及已关联整单共用的只读比对投影；不读取数据库或改变审核。"""

from decimal import Decimal

from ..mapper import allocation_mapper as mapper
from ..policy.comparison_policy import text, tier
from ..vo.matching_vo import GroupItem, GroupLine, GroupOrder, GroupView


def comparison_view(key, rows, compared, lines, reasons, confirm, reject):
    orders = {}
    for row in rows:
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
    lowest = min(
        (confidence for _, confidence, _ in compared.values() if confidence is not None),
        default=None if compared else Decimal(0),
    )
    return GroupView(
        id=key,
        orders=[GroupOrder(**order) for order in orders.values()],
        items=items,
        confidence=text(lowest),
        tier=tier(lowest),
        noteReasons=reasons,
        confirm=confirm,
        reject=reject,
        allocationIds=[str(row["id"]) for row in rows],
    )
