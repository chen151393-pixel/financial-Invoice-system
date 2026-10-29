"""卷与平方米不同口径的回归：页面、合并、幅度一致，冻结开票数量不被替换。"""

from copy import deepcopy
from decimal import Decimal

import pytest
from backend.modules.review.mapper.declaration_mapper import purchase_line, review_lines
from backend.modules.review.policy.auto_review_policy import auto_review_reasons, margin_alert
from backend.modules.review.policy.margin_policy import declared_margin
from backend.modules.review.policy.purchase_display_policy import group_purchase_lines
from backend.tests.test_review import events as events
from backend.tests.test_review import group
from backend.tests.test_review import service as service
from backend.tests.test_source_storage import bundle, customs, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_source_storage import purchase as source_purchase


def purchase(quantity="100", declared="1525", amount="8113", price="81.13"):
    return {
        "id": 1,
        "purchase_order_id": 1,
        "source_line_key": "line-1",
        "quantity": Decimal(quantity),
        "unit": "卷",
        "declared_quantity": Decimal(declared),
        "declared_unit": "平方米",
        "unit_price": Decimal(price),
        "amount": Decimal(amount),
        "amount_status": "matched",
        "declaration_name": "膜",
        "item_name": "膜",
        "specification": "0.305×50m",
    }


ORDER = {
    "id": 1,
    "ns_internal_id": "200",
    "supplier_id": 1,
    "company_id": 1,
    "parent_order_no": "PO-1",
    "order_no": "SUB-1",
    "supplier_name": "供应商",
    "currency": "CNY",
}
CUSTOMS = {
    "declared_quantity": Decimal("1525"),
    "declared_unit": "平方米",
    "declared_unit_price": Decimal("5.414162"),
    "currency": "CNY",
    "sales_order_no": "SO1",
}


@pytest.mark.parametrize(
    "row,expected",
    [(purchase(), "81.13"), (purchase("80", "1220", "18452.6", "230.6575"), "230.6575")],
)
def test_screenshot_values_share_declared_quantity_unit_and_tax_inclusive_price(row, expected):
    before = deepcopy(row)
    shown = purchase_line(ORDER, row)
    result = declared_margin(
        {**CUSTOMS, "declared_quantity": row["declared_quantity"]}, [row], {1: ORDER}, {}
    )
    assert (shown.quantity, shown.unit, shown.price, shown.scope) == (
        str(row["declared_quantity"]),
        "平方米",
        expected,
        "declared",
    )
    assert result["purchase"] == row["amount"] / row["declared_quantity"]
    assert "原采购数量" in shown.note and str(row["unit_price"]) in shown.note
    (frozen,) = review_lines({"orders": [ORDER], "purchase_lines": [row], "links": []})
    assert (frozen["quantity"], frozen["unit"], frozen["amount"]) == (row["quantity"], "卷", row["amount"])
    assert row == before


def test_four_pvc_rows_sum_declared_quantities_and_amounts_before_dividing():
    rows = [
        {**purchase("20", "305", amount, price), "id": index}
        for index, (amount, price) in enumerate(
            [("4000", "200"), ("4500", "225"), ("5000", "250"), ("4952.6", "247.63")], 1
        )
    ]
    (shown,) = group_purchase_lines([purchase_line(ORDER, row).model_dump() for row in rows])
    assert (shown["quantity"], shown["unit"], shown["price"], shown["amount"]) == (
        "1220",
        "平方米",
        "230.66",
        "18452.6",
    )
    assert len(shown["members"]) == 4
    result = declared_margin(
        {**CUSTOMS, "declared_unit_price": Decimal("15.392742"), "declared_quantity": Decimal("1220")},
        rows,
        {1: ORDER},
        {},
    )
    assert result["purchase"] == Decimal("18452.6") / Decimal("1220")
    assert result["status"] == "ok"
    assert result["margin"] == Decimal("1.74")


@pytest.mark.parametrize(
    "field,value",
    [
        ("declared_quantity", None),
        ("declared_quantity", Decimal(0)),
        ("declared_quantity", Decimal(-1)),
        ("declared_unit", None),
        ("amount", None),
    ],
)
def test_missing_or_invalid_declared_basis_never_falls_back_to_purchase_quantity(field, value):
    row = {**purchase(), field: value}
    shown = purchase_line(ORDER, row)
    assert shown.price == "81.13"  # 报关字段缺失不影响原始采购含税单价
    if field == "declared_quantity" and value is None:
        assert shown.quantity == ""
    result = declared_margin(CUSTOMS, [row, purchase()], {1: ORDER}, {})
    assert result["status"] == "unavailable" and result["purchase"] is None


def test_declared_unit_mismatch_blocks_price_comparison_even_when_purchase_units_match():
    row = {**purchase(), "unit": "平方米", "declared_unit": "千克"}
    result = declared_margin(CUSTOMS, [row], {1: ORDER}, {})
    assert result["status"] == "unavailable" and "报关单位不一致" in result["note"]


def test_saved_source_and_materialized_page_preserve_both_quantity_bases(ns, engine, service):
    order, declaration = source_purchase(), customs()
    for _, row in order[2]:
        row.update(
            custrecord_swc_subpo_item_qty=Decimal("100"),
            custrecord_swc_subpo_item_unit="卷",
            custrecord_swc_subpo_item_bgqty=Decimal("1525"),
            custrecord_swc_subpo_item_bgunit="平方米",
            custrecord_swc_subpo_item_ratewithrate=Decimal("81.13"),
            custrecord_swc_subpo_item_amountwithtax=Decimal("8113"),
        )
    for _, row in declaration[2]:
        row.update(
            custrecord_swc_delare_quantity=Decimal("1525"),
            custrecord_swc_delare_unit="平方米",
            custrecord_swc_grossamountzj=Decimal("0.8"),
        )
    save(ns, engine, bundle([order], [declaration]))
    result = group(service, "CD870")
    assert not result.unlinkedLines
    for line in result.customsLines:
        (child,) = line.purchaseLines
        assert (child.quantity, child.unit, child.price, child.purchaseQuantity, child.purchaseUnit) == (
            "1525",
            "平方米",
            "81.13",
            "100",
            "卷",
        )
        assert line.combinedPurchaseUnitPrice == "5.32"
        assert line.marginStatus == "ok"


def test_original_tax_inclusive_price_is_not_recomputed_from_rounded_amount():
    row = purchase(amount="8113.01")
    assert purchase_line(ORDER, row).price == "81.13"
    row["unit_price"] = None
    assert purchase_line(ORDER, row).price == ""


@pytest.mark.parametrize("quantity", ["1524", "1526", "1525.00000001"])
def test_quantity_mismatch_precedes_price_and_blocks_low_price_judgement(quantity):
    row = purchase(amount="999999")
    result = declared_margin({**CUSTOMS, "declared_quantity": Decimal(quantity)}, [row], {1: ORDER}, {})
    assert result["status"] == "unavailable"
    assert result["margin"] is None and result["declared"] is None and result["purchase"] is None
    assert result["note"].startswith("数量口径待核对（报关行 ")
    assert "子采购报关合计 1525" in result["note"]
    assert not margin_alert([result])
    reasons = auto_review_reasons("pending", False, 0, [row], True, [result])
    assert any("数量口径待核对" in reason for reason in reasons)
    # 数量先核对；金额/汇率缺失也不能掩盖已经查明的数量差异。
    assert (
        declared_margin(
            {**CUSTOMS, "declared_quantity": Decimal(quantity), "currency": "USD"},
            [{**row, "amount": None}],
            {1: ORDER},
            {},
        )["note"]
        == result["note"]
    )


@pytest.mark.parametrize("quantity", [None, Decimal(0), Decimal(-1)])
def test_invalid_customs_quantity_requires_check_even_when_unit_price_exists(quantity):
    result = declared_margin({**CUSTOMS, "declared_quantity": quantity}, [purchase()], {1: ORDER}, {})
    assert result["status"] == "unavailable"
    assert "数量口径待核对" in result["note"]


def test_equal_quantities_sum_across_suborders_and_preserve_real_low_price_result():
    first = purchase("1625", "1625", "29575", "18.2")
    second = {**purchase("5375", "5375", "83425", "15.52"), "purchase_order_id": 2}
    result = declared_margin(
        {**CUSTOMS, "declared_quantity": Decimal("7000"), "declared_unit_price": Decimal("14.3736")},
        [first, second],
        {1: ORDER, 2: {**ORDER, "id": 2}},
        {},
    )
    assert result["status"] == "negative" and result["margin"] == Decimal("-12.31")


def test_quantity_comparison_uses_decimal_equality_without_rounding():
    rows = [purchase("1", "0.1", "0.1", "0.1"), purchase("1", "0.2", "0.2", "0.2")]
    result = declared_margin({**CUSTOMS, "declared_quantity": Decimal("0.30000000")}, rows, {1: ORDER}, {})
    assert result["status"] == "ok"


def test_materialized_page_does_not_report_low_price_for_quantity_mismatch(ns, engine, service):
    order, declaration = source_purchase(amounts=("99999", "99999")), customs()
    for _, row in order[2]:
        row["custrecord_swc_subpo_item_bgunit"] = "个"
        row["custrecord_swc_subpo_item_bgqty"] = Decimal("9")
    save(ns, engine, bundle([order], [declaration]))
    result = group(service, "CD870")
    assert not result.marginAlert and not result.autoReview.eligible
    for line in result.customsLines:
        assert line.marginStatus == "unavailable" and line.margin == ""
        assert line.marginNote == "数量口径待核对（报关行 10，子采购报关合计 9）"
        assert line.combinedPurchaseUnitPrice == "" and line.declaredUnitPriceCny == ""
