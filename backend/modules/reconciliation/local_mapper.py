"""已入库来源的只读视图；订单金额不可冒充本次已报关分摊金额。"""

from collections import defaultdict
from decimal import Decimal

from .mapper import declaration, unique_text
from .vo import CustomsLine, Declaration, PurchaseLine, ReviewState


def text(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        # 仅去掉数据库 DECIMAL 固定标度的尾零，保留全部有效小数，不经浮点或四舍五入。
        rendered = format(value, "f")
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
    return str(value)


def purchase_quantity_unit(row):
    """NS 子采购汇总行使用子单自己的报关数量与单位，必须成对展示。"""
    quantity = row.get("declaration_quantity")
    unit = row.get("declaration_unit")
    if quantity is not None and unit:
        return text(quantity), text(unit), "子采购报关数量和单位"
    return text(row["quantity"]), text(row["unit_name"]), "子采购原始数量和单位"


def purchase_line(order, row):
    quantity, unit, basis = purchase_quantity_unit(row)
    return PurchaseLine(
        id=f"local-purchase-{row['id']}",
        name=text(row["declaration_name"] or row["item_name"]),
        model=text(row["specification"]),
        parent=text(order["parent_order_no"]),
        child=text(order["order_no"]),
        supplier=text(order["supplier_name"]),
        quantity=quantity,
        unit=unit,
        price=text(row["tax_inclusive_price"]),
        amount=text(row["amount"]),
        currency=text(order["currency_code"]),
        scope="order",
        note=(
            f"通过 NS 子采购单的报关单引用关联。当前显示{basis}和子单金额，供财务核对；未逐行分摊的原值不自动计为开票额度。"
        ),
    )


def declarations(data):
    details, purchases, lines = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in data["details"]:
        details[row["customs_declaration_id"]].append(row)
    for row in data["purchases"]:
        purchases[row["customs_declaration_id"]].append(row)
    for row in data["lines"]:
        lines[row["purchase_order_id"]].append(row)
    groups = []
    for head in data["heads"]:
        relation = data.get("relations", {}).get(head["id"])
        comparison = relation.get("comparison") if relation else None
        if comparison:
            payload = comparison["payload"]
            group = declaration(payload["group"], payload["version"])
            group.id = f"local-{head['id']}"
            group.account = text(head["ns_account"])
            for line in group.unlinkedLines:
                line.scope = "order"
            group.review = ReviewState(
                status="pending",
                label="待审核",
                allowed=False,
                reason="",
            )
            groups.append(group)
            continue
        bindings = relation.get("lineRelations", {}) if relation else {}
        rows_by_customs = defaultdict(list)
        purchase_rows = []
        for order in purchases[head["id"]]:
            for row in lines[order["id"]]:
                item = purchase_line(order, row)
                purchase_rows.append(item)
                rows_by_customs[bindings.get(str(row["id"]))].append(item)
        customs_rows = [
            CustomsLine(
                id=f"local-customs-{row['id']}",
                lineNo=row["line_no"] or index + 1,
                name=text(row["declaration_name"]),
                model=text(row["specification"]),
                quantity=text(row["declared_quantity"]),
                unit=text(row["declared_unit"]),
                price=text(row["unit_price"]),
                amount=text(row["amount"]),
                currency=text(row["currency_code"]),
                purchaseCount=len(rows_by_customs[str(row["id"])]),
                purchaseLines=rows_by_customs[str(row["id"])],
            )
            for index, row in enumerate(details[head["id"]])
        ]
        # 来源诊断保存在business证据表；财务人工核对不再经过机器关联核实步骤。
        warnings = []
        groups.append(
            Declaration(
                id=f"local-{head['id']}",
                account=text(head["ns_account"]),
                recordNumber=text(head["record_no"]),
                declaration=text(head["declaration_no"]),
                pl=unique_text(
                    [text(row["pl_no"]) for row in details[head["id"]]]
                    + [text(order["pl_no"]) for order in purchases[head["id"]]]
                ),
                company=unique_text(text(row["company_name"]) for row in details[head["id"]]),
                customsCount=len(customs_rows),
                purchaseCount=len(purchase_rows),
                customsLines=customs_rows,
                unlinkedLines=rows_by_customs[None],
                warnings=warnings,
                review=ReviewState(status="pending", label="待审核", allowed=False, reason=""),
            )
        )
    return groups
