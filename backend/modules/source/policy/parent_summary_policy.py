"""Packing 全部缺失时，使用双方显式母采购引用与整组报关数量定位汇总行。"""

from decimal import Decimal

from .purchase_summary_policy import positive_quantity


def parent_summary_bindings(candidates, groups, blocked_headers, diagnostics):
    """同一母单、PL、公司、销售单、报关品名、单位仅允许一个汇总候选。"""
    bindings = {}
    for key, members in groups.items():
        targets = candidates.get(key, [])
        # 同一母单可能跨货源地或多条同名汇总行，不能拿数量凑出其中一条。
        if key[:4] in blocked_headers or len(targets) != 1 or any(not valid for _, _, valid in members):
            continue
        quantities = [positive_quantity(quantity) for _, quantity, _ in members]
        if any(quantity is None for quantity in quantities):
            continue
        total = sum(quantities, Decimal(0))
        identity, declared_quantity = targets[0]
        if positive_quantity(declared_quantity) != total:
            continue
        bindings.update({line_id: identity for line_id, _, _ in members})
        pl, company, parent, sales, name, unit = key
        diagnostics.append(
            {
                "code": "PARENT_SUMMARY_UNIT_QUANTITY",
                "customsLineId": identity,
                "purchaseLineIds": [line_id for line_id, _, _ in members],
                "plId": pl,
                "companyId": company,
                "parentPurchaseId": parent,
                "salesId": sales,
                "declarationName": name,
                "purchaseUnitId": unit,
                "purchaseQuantity": str(total),
                "message": "本地 Packing 缺失，按双方显式母采购引用、PL、公司、销售单、报关品名、单位及整组数量唯一定位。",
            }
        )
    return bindings
