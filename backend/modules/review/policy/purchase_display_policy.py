"""同一报关行内的采购展示合并；保留原行，不参与审核冻结与关联定位。"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal


def number(value):
    if value is None:
        return ""
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def total(rows, field):
    if any(row[field] == "" for row in rows):
        return None
    return sum((Decimal(row[field]) for row in rows), Decimal(0))


def group_purchase_lines(lines):
    groups = defaultdict(list)
    for line in lines:
        # 口径、币种与母单也须相同；关键字段缺失时不把未知来源合在一起。
        fields = ("child", "supplier", "name", "unit", "purchaseUnit", "currency", "scope", "parent")
        key = tuple(line[field] for field in fields)
        if not all(
            line[field] for field in ("child", "supplier", "name", "unit", "purchaseUnit", "currency")
        ):
            key += (line["id"],)
        groups[key].append(line)
    result = []
    for members in groups.values():
        first = members[0]
        if len(members) == 1:
            result.append({**first, "members": []})
            continue
        quantity, amount = total(members, "quantity"), total(members, "amount")
        purchase_quantity = total(members, "purchaseQuantity")
        price = (
            amount / purchase_quantity
            if amount is not None
            and purchase_quantity is not None
            and all(Decimal(row["purchaseQuantity"]) > 0 for row in members)
            else None
        )
        models = list(dict.fromkeys(row["model"] for row in members if row["model"]))
        result.append(
            {
                **first,
                "id": f"group-{first['id']}",
                "quantity": number(quantity),
                "purchaseQuantity": number(purchase_quantity),
                "amount": number(amount),
                "price": number(price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                if price is not None
                else "",
                "model": "、".join(models),
                "note": f"合并 {len(members)} 条原始采购行；展示报关数量，合并采购单价 = 含税总金额 / 总采购数量。"
                + ("金额或数量缺失，或总数量非正数，无法计算合并单价。" if price is None else ""),
                "members": members,
            }
        )
    return result
