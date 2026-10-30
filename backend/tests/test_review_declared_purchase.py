"""同一报关行双单价比较；子采购展示、合并与冻结继续保留原口径。"""

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
    "quantity": Decimal("100"),
    "unit": "卷",
    "unit_price": Decimal("5.32"),
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
    assert result["original"] == CUSTOMS["unit_price"]
    assert "原采购数量" in shown.note and str(row["unit_price"]) in shown.note
    (frozen,) = review_lines({"orders": [ORDER], "purchase_lines": [row], "links": []})
    assert (frozen["quantity"], frozen["unit"], frozen["amount"]) == (row["quantity"], "卷", row["amount"])
    assert row == before


def test_purchase_display_grouping_does_not_supply_margin_comparison_price():
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
    assert result["original"] == Decimal("5.32")
    assert result["status"] == "ok"
    assert result["margin"] == Decimal("65.44")


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
def test_missing_purchase_basis_does_not_change_customs_price_margin(field, value):
    row = {**purchase(), field: value}
    shown = purchase_line(ORDER, row)
    assert shown.price == "81.13"  # 报关字段缺失不影响原始采购含税单价
    if field == "declared_quantity" and value is None:
        assert shown.quantity == ""
    result = declared_margin(CUSTOMS, [row, purchase()], {1: ORDER}, {})
    assert result["status"] == "ok" and result["original"] == CUSTOMS["unit_price"]


def test_purchase_unit_mismatch_does_not_block_customs_price_comparison():
    row = {**purchase(), "unit": "平方米", "declared_unit": "千克"}
    result = declared_margin(CUSTOMS, [row], {1: ORDER}, {})
    assert result["status"] == "ok" and result["margin"] == Decimal("1.74")


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
        assert line.originalUnitPriceCny == "21.3"
        assert line.declaredUnitPriceCny == "5.68"
        assert line.originalPriceUnit == "千克" and line.declaredPriceUnit == "平方米"
        assert line.marginStatus == "negative" and line.margin == "-275.00%"


def test_original_tax_inclusive_price_is_not_recomputed_from_rounded_amount():
    row = purchase(amount="8113.01")
    assert purchase_line(ORDER, row).price == "81.13"
    row["unit_price"] = None
    assert purchase_line(ORDER, row).price == ""


@pytest.mark.parametrize(
    "quantity", [None, Decimal(0), Decimal(-1), Decimal("1524"), Decimal("1525.00000001")]
)
def test_existing_prices_do_not_require_matching_or_valid_quantity(quantity):
    row = purchase(amount="999999")
    result = declared_margin({**CUSTOMS, "declared_quantity": quantity}, [row], {1: ORDER}, {})
    assert result["status"] == "ok" and result["margin"] == Decimal("1.74")
    assert not margin_alert([result])


@pytest.mark.parametrize("price", [None, Decimal(0), Decimal(-1)])
def test_invalid_original_price_is_not_replaced_by_total_or_purchase_amount(price):
    result = declared_margin({**CUSTOMS, "unit_price": price, "amount": Decimal("8113")}, [], {}, {})
    assert result["status"] == "unavailable" and "报关行单价" in result["note"]
    assert result["original"] is None and result["margin"] is None


@pytest.mark.parametrize("price", [Decimal(0), Decimal(-1)])
def test_invalid_present_declared_price_does_not_trigger_estimate(price):
    result = declared_margin({**CUSTOMS, "declared_unit_price": price, "amount": Decimal("8113")}, [], {}, {})
    assert result["status"] == "unavailable" and "须大于 0" in result["note"]


def test_cd000849_compares_two_212_prices_instead_of_113000_purchase_total():
    first = purchase("1625", "1625", "29575", "18.2")
    second = {**purchase("5375", "5375", "83425", "15.52"), "purchase_order_id": 2}
    customs_row = {
        **CUSTOMS,
        "unit": "个",
        "declared_unit": "个",
        "quantity": Decimal("7000"),
        "declared_quantity": Decimal("7000"),
        "amount": Decimal("14840"),
        "unit_price": Decimal("2.12"),
        "declared_unit_price": Decimal("2.12"),
        "currency": "USD",
    }
    orders = {1: {**ORDER, "sales_order_id": 9}, 2: {**ORDER, "id": 2, "sales_order_id": 9}}
    sales = {9: {"id": 9, "order_no": "SO1", "currency": "USD", "exchange_rate": Decimal("6.78")}}
    result = declared_margin(customs_row, [first, second], orders, sales)
    assert result["status"] == "ok" and result["margin"] == Decimal("0.00")
    assert result["original"] == result["declared"] == Decimal("14.3736")
    assert (
        declared_margin({**customs_row, "declared_unit_price": None}, [first, second], orders, sales)
        == result
    )


def test_missing_child_amount_still_blocks_auto_review_but_not_margin():
    row = {**purchase(), "amount": None}
    result = declared_margin(CUSTOMS, [row], {1: ORDER}, {})
    assert result["status"] == "ok"
    assert auto_review_reasons("pending", False, 0, [row], True, [result]) == ["子采购含税金额缺失"]


def test_materialized_page_uses_customs_prices_despite_purchase_quantity_mismatch(ns, engine, service):
    order, declaration = source_purchase(amounts=("99999", "99999")), customs()
    for _, row in order[2]:
        row["custrecord_swc_subpo_item_bgunit"] = "个"
        row["custrecord_swc_subpo_item_bgqty"] = Decimal("9")
    save(ns, engine, bundle([order], [declaration]))
    result = group(service, "CD870")
    assert result.marginAlert and not result.autoReview.eligible
    for line in result.customsLines:
        assert line.marginStatus == "negative" and line.margin == "-100.00%"
        assert line.marginNote == "报关单价低于报关行单价"
        assert line.originalUnitPriceCny == "21.3" and line.declaredUnitPriceCny == "10.65"
