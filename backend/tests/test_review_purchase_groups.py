"""采购展示合并：数量金额精确汇总、分组边界、缺值以及原始明细保留。"""

import pytest
from backend.modules.review.policy.purchase_display_policy import group_purchase_lines


def line(identity, **values):
    return {
        "id": identity,
        "child": "SUB-1",
        "parent": "PO-1",
        "supplier": "供应商甲",
        "name": "相纸",
        "unit": "千克",
        "currency": "CNY",
        "scope": "order",
        "quantity": "2",
        "purchaseQuantity": "2",
        "purchaseUnit": "千克",
        "amount": "20",
        "price": "10",
        "model": "A4",
        "note": "原始说明",
        **values,
    }


def test_merged_price_uses_total_amount_over_total_quantity_and_keeps_members():
    first, second = (
        line("1"),
        line("2", quantity="8", purchaseQuantity="8", amount="160", price="20", model="A3"),
    )
    (merged,) = group_purchase_lines([first, second])
    assert (merged["quantity"], merged["amount"], merged["price"]) == ("10", "180", "18")
    assert merged["members"] == [first, second]
    assert merged["model"] == "A4、A3"
    assert first["amount"] == "20" and second["amount"] == "160"


@pytest.mark.parametrize(
    "field", ["child", "supplier", "name", "unit", "purchaseUnit", "currency", "scope", "parent"]
)
def test_distinct_group_fields_never_merge(field):
    assert len(group_purchase_lines([line("1"), line("2", **{field: "不同值"})])) == 2


@pytest.mark.parametrize("field", ["child", "supplier", "name", "unit", "purchaseUnit", "currency"])
def test_unknown_group_fields_remain_separate(field):
    assert len(group_purchase_lines([line("1", **{field: ""}), line("2", **{field: ""})])) == 2


def test_amounts_remain_decimal_and_missing_values_are_not_partial_totals():
    (merged,) = group_purchase_lines([line("1", amount="9007199254740993.01"), line("2", amount="0.02")])
    assert merged["amount"] == "9007199254740993.03"
    (missing,) = group_purchase_lines([line("1"), line("2", amount="")])
    assert missing["amount"] == "" and missing["price"] == "" and missing["quantity"] == "4"
    (zero,) = group_purchase_lines(
        [line("1", quantity="0", purchaseQuantity="0"), line("2", quantity="0", purchaseQuantity="0")]
    )
    assert zero["price"] == "" and "无法计算" in zero["note"]
