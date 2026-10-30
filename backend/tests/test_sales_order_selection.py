"""报关行销售单：去显示前缀后完整单号唯一匹配，不借用其他销售单汇率。"""

from decimal import Decimal

import pytest
from backend.modules.review.policy.margin_policy import declared_margin
from backend.modules.source.public import pick_sales_order

FIRST = {"id": 1, "order_no": "YEJ260612-02/1426号货柜", "currency": "USD", "exchange_rate": Decimal("6.74")}
SECOND = {
    "id": 2,
    "order_no": "YEJ260723-09//阿根廷货柜",
    "currency": "USD",
    "exchange_rate": Decimal("6.76"),
}


@pytest.mark.parametrize(
    "prefix", ["", "销售订单 #", "销售订单#", "销售单 ＃ ", "Sales Order #", "sales order # "]
)
def test_display_prefix_and_outer_whitespace_allow_unique_full_match(prefix):
    number = f"  {prefix}{FIRST['order_no']}  "
    assert pick_sales_order(number, [SECOND, FIRST, FIRST]) == (FIRST, "")
    shown = {**FIRST, "order_no": f"销售订单 #{FIRST['order_no']}"}
    assert pick_sales_order(FIRST["order_no"], [SECOND, shown]) == (shown, "")


@pytest.mark.parametrize(
    "number",
    [
        "YEJ260612-02",
        "YEJ260612-02/1426号货柜2",
        "YEJ260612-02//1426号货柜",
        "yej260612-02/1426号货柜",
        "YEJ260612-02/1426 号货柜",
    ],
)
def test_partial_number_and_changed_suffix_do_not_match_even_one_candidate(number):
    assert pick_sales_order(f"销售订单 #{number}", [FIRST]) == (None, "未匹配到对应销售单")


@pytest.mark.parametrize("number", [None, "", "  ", "销售订单 #"])
def test_missing_number_does_not_fall_back_to_only_candidate(number):
    assert pick_sales_order(number, [FIRST]) == (None, "报关行销售单号缺失")


@pytest.mark.parametrize("rate", [Decimal("6.74"), Decimal("6.76")])
def test_different_sales_ids_with_same_full_number_are_ambiguous_even_if_rates_equal(rate):
    duplicate = {**FIRST, "id": 3, "exchange_rate": rate}
    assert pick_sales_order(f"销售订单 #{FIRST['order_no']}", [FIRST, duplicate]) == (
        None,
        "对应销售单不唯一",
    )


def test_no_candidates_or_wrong_number_never_supplies_a_rate():
    assert pick_sales_order(FIRST["order_no"], [None]) == (None, "未匹配到对应销售单")
    assert pick_sales_order("NO-MATCH", [FIRST, SECOND]) == (None, "未匹配到对应销售单")


@pytest.mark.parametrize("sale", [FIRST, SECOND])
def test_each_customs_line_uses_only_its_own_matching_sales_rate(sale):
    customs = {
        "sales_order_no": f"销售订单 #{sale['order_no']}",
        "currency": "USD",
        "unit_price": Decimal("90.39"),
        "declared_unit_price": Decimal("90.39"),
        "declared_unit": "台",
        "declared_quantity": Decimal("375"),
    }
    children = [
        {"purchase_order_id": 10, "declared_quantity": Decimal("27"), "declared_unit": "台"},
        {"purchase_order_id": 11, "declared_quantity": Decimal("348"), "declared_unit": "台"},
    ]
    orders = {10: {"sales_order_id": 1}, 11: {"sales_order_id": 2}}
    sales = {1: FIRST, 2: SECOND}
    result = declared_margin(customs, children, orders, sales)
    assert result["status"] == "ok" and result["margin"] == Decimal("0.00")
    assert result["original"] == result["declared"] == Decimal("90.39") * sale["exchange_rate"]
    # 目标销售单缺汇率时，即使另一张有值也不能借用。
    sales[sale["id"]] = {**sale, "exchange_rate": None}
    missing = declared_margin(customs, children, orders, sales)
    assert missing["status"] == "unavailable" and missing["note"] == "销售单汇率待同步，无法计算"
