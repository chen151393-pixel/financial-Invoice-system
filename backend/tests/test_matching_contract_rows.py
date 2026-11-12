"""发票按 NS 子采购合同的合并行开具（2026-11-09）：报关品名 + 单位合并后整体定位发票行。

数据按真实单 YE-YH20260804-P250-1 简化：同名“PVC膜”多条明细合并为一行，“pvc膜”单独一行；
发票两行品名都是“*塑料制品*PVC膜”，只能靠合同行数量、金额合计区分，且第一行金额有 0.01 尾差。
"""

from decimal import Decimal

from backend.modules.matching.policy.contract_row_policy import contract_rows
from backend.modules.matching.policy.order_group_policy import fit_all, order_parts, short_lines, totals

INVOICE = {
    "status": "normal",
    "detail_status": "complete",
    "currency": "CNY",
    "remark": "YEL260731-14(41745747) P250",
    "seller_name": "安徽垣锽新材料科技有限公司",
    "buyer_name": "上海毅鑫实业有限公司",
    "buyer_name_normalized": "上海毅鑫实业有限公司",
}
# (报关品名, 数量, 含税金额)；合同合并为 PVC膜 2280 卷 / 8988.48 与 pvc膜 648 卷 / 4822.42
LINES = {
    1: ("PVC膜", "1464", "5446.08"),
    2: ("PVC膜", "408", "2203.20"),
    3: ("pvc膜", "648", "4822.42"),
    4: ("PVC膜", "408", "1339.20"),
}


def line(name):
    return {
        "active": True,
        "basis_reason": "",
        "currency": "CNY",
        "purchase_order_id": 2423,
        "order_no": "YE-YH20260804-P250-1",
        "parent_order_no": "采购订单 #YE-YH20260804-P250",
        "sales_order_no": "YEL260731-14",
        "supplier_name": "安徽垣锽新材料科技有限公司",
        "company_name": "上海毅鑫实业有限公司",
        "company_name_normalized": "上海毅鑫实业有限公司",
        "item_name": "刻字贴",
        "declaration_name": name,
        "unit_name": "卷",
        "tax_rate": Decimal("0.13"),
    }


def world():
    lines = {line_id: line(name) for line_id, (name, _, _) in LINES.items()}
    tasks = {
        line_id: {
            "purchase_basis_id": 900 + line_id,
            "status": "open",
            "expected_quantity": Decimal(quantity),
            "expected_amount": Decimal(amount),
        }
        for line_id, (_, quantity, amount) in LINES.items()
    }
    bases = {line_id: {"id": 900 + line_id, "allowed": True} for line_id in LINES}
    return lines, tasks, bases


def item(item_id, quantity, amount, tax):
    return {
        "id": item_id,
        "item_name": "*塑料制品*PVC膜",
        "unit": "卷",
        "quantity": Decimal(quantity),
        "amount_including_tax": Decimal(amount),
        "tax_amount": Decimal(tax),
    }


# 第 1 行票面 8988.47，比合同行少 0.01 尾差
ITEMS = [item(1, "2280", "8988.47", "1034.07"), item(2, "648", "4822.42", "554.79")]


def test_contract_rows_merge_by_exact_declaration_name_and_unit():
    lines, _, _ = world()
    assert contract_rows(lines) == [[1, 2, 4], [3]]
    lines[4]["unit_name"] = "米"
    assert contract_rows(lines) == [[1, 2], [3], [4]]
    # 报关品名为空时退回商品名称
    lines[2]["declaration_name"] = None
    assert contract_rows(lines)[1:] == [[2], [3], [4]]


def test_same_name_invoice_lines_are_located_by_contract_row_totals():
    lines, tasks, bases = world()
    parts, block = order_parts(INVOICE, ITEMS, lines, tasks, bases, None)
    assert block == ""
    assert {part["purchase_line_id"]: part["invoice_item_id"] for part in parts} == {1: 1, 2: 1, 4: 1, 3: 2}
    assert totals(parts) == {
        1: (Decimal(2280), Decimal("8988.48")),
        2: (Decimal(648), Decimal("4822.42")),
    }


def test_rounding_tail_is_not_closed_by_difference():
    lines, tasks, bases = world()
    parts, _ = order_parts(INVOICE, ITEMS, lines, tasks, bases, None)
    rows = fit_all(parts, {found["id"]: found for found in ITEMS})
    allocations = [
        {
            "quantity": row["quantity"],
            "amount": row["amount"],
            "checks": {
                "orderShare": {"quantity": str(row["share_quantity"]), "amount": str(row["share_amount"])}
            },
        }
        for row in rows
    ]
    # 记账不超过票面：最后一条明细少记 0.01，但数量足额，属于尾差
    assert sum(row["amount"] for row in rows if row["invoice_item_id"] == 1) == Decimal("8988.47")
    assert short_lines(allocations) == []
    # 金额差超过尾差仍按发票少处理
    allocations[0]["amount"] -= Decimal("0.02")
    assert short_lines(allocations) == [allocations[0]]


def test_identical_contract_rows_still_need_manual_choice():
    lines, tasks, bases = world()
    # 两张发票行与合同行完全相同时无法区分，仍交人工选择
    same = [item(1, "2928", "13810.90", "1588.86"), item(2, "2928", "13810.90", "1588.86")]
    lines[3]["declaration_name"] = "PVC膜"
    parts, block = order_parts(INVOICE, same, lines, tasks, bases, None)
    assert parts == [] and "须人工选择发票行" in block
