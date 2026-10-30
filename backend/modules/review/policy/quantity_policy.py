"""单价比较前校验报关行与关联子采购行的报关数量；不参与价格折算。"""

from decimal import Decimal

from backend.modules.source.public import unit_label


def quantity_issue(customs_row, purchase_rows, unit_names=None):
    if not purchase_rows:
        return "没有行级关联的子采购行，数量口径待核对"
    customs_unit = unit_label(customs_row["declared_unit"], unit_names)
    if not customs_unit or any(not unit_label(row["declared_unit"], unit_names) for row in purchase_rows):
        return "报关单位缺失，数量口径待核对"
    if any(unit_label(row["declared_unit"], unit_names) != customs_unit for row in purchase_rows):
        return "报关行与子采购行报关单位不一致，不计算申报幅度"
    declared_quantity = customs_row["declared_quantity"]
    if declared_quantity is None:
        return "数量口径待核对（报关行数量缺失）"
    if declared_quantity <= 0:
        return "数量口径待核对（报关行数量须大于 0）"
    if any(row["declared_quantity"] is None for row in purchase_rows):
        return "数量口径待核对（子采购报关数量缺失）"
    if any(row["declared_quantity"] <= 0 for row in purchase_rows):
        return "数量口径待核对（子采购报关数量须大于 0）"
    # 按同一报关行的全部原始关联行汇总，不使用采购数量、展示合并行或价格容差。
    quantity = sum((row["declared_quantity"] for row in purchase_rows), Decimal(0))
    if quantity != declared_quantity:
        return (
            f"数量不一致（报关行 {declared_quantity.normalize():f}，子采购报关合计 {quantity.normalize():f}）"
        )
    return ""
