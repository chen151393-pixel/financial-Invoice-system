"""采购未税 USD 单价：已核实样本、采购数量分母、多单归属及缺失数据。"""

from copy import deepcopy
from decimal import Decimal as D

import pytest
from backend.modules.review.mapper.declaration_mapper import declaration, line_bindings, review_lines
from backend.modules.review.policy.margin_policy import declared_margin
from backend.modules.review.policy.purchase_price_policy import purchase_price
from backend.modules.source.public import DeclarationService
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns

SALES = {9: {"id": 9, "order_no": "SO-1", "currency": "USD", "exchange_rate": D("6.70")}}
ORDERS = {1: {"sales_order_id": 9, "currency": "CNY"}, 2: {"sales_order_id": 9, "currency": "CNY"}}
CUSTOMS = {
    "sales_order_no": "销售订单 #SO-1",
    "currency": "USD",
    "unit_price": D("999"),
    "quantity": D("15000"),
    "unit": "个",
    "declared_quantity": D("15000"),
    "declared_unit": "个",
    "declared_unit_price": D("1.06"),
}


def row(identity=1, order=1, quantity="9000", gross="68400", tax="0.13"):
    return {
        "id": identity,
        "purchase_order_id": order,
        "quantity": D(quantity),
        "unit": "个",
        "parent_purchase_unit": "个",
        "declared_quantity": D(quantity),
        "declared_unit": "个",
        "amount": D(gross),
        "tax_rate": D(tax),
        "unit_price": D("999999"),
    }


def test_cd000962_uses_two_original_purchase_quantities_and_line_net_amounts():
    rows = [row(), row(2, 2, "6000", "38400")]
    before = deepcopy(rows)
    price = purchase_price(CUSTOMS, rows, ORDERS, SALES)
    assert price["quantity"] == D("15000")
    assert price["cny"] * D("15000") == D("94513.27")
    assert price["usd"].quantize(D("0.000001")) == D("0.940431")
    assert rows == before
    margin = declared_margin(CUSTOMS, rows, ORDERS, SALES)
    assert margin["original"] == price["cny"]
    assert margin["declared"] == D("7.102")
    assert margin["status"] == "ok"
    assert margin["margin"] == D("11.28")
    assert declared_margin({**CUSTOMS, "unit_price": None}, rows, ORDERS, SALES) == margin


def test_customs_quantity_or_unit_change_never_changes_purchase_price():
    rows = [row(quantity="100", gross="1130")]
    a = purchase_price(CUSTOMS, rows, ORDERS, SALES)
    for changed_customs in [
        {**CUSTOMS, "declared_quantity": D("500"), "declared_unit": "千克"},
        {**CUSTOMS, "quantity": None, "unit": None, "declared_quantity": None},
    ]:
        assert purchase_price(changed_customs, rows, ORDERS, SALES) == a
        assert declared_margin(changed_customs, rows, ORDERS, SALES)["purchase"] == a
    rows[0]["declared_quantity"] = D("500")
    rows[0]["declared_unit"] = "千克"
    assert purchase_price(CUSTOMS, rows, ORDERS, SALES) == a


def test_mixed_tax_rates_are_removed_per_line_before_summing():
    price = purchase_price(
        CUSTOMS, [row(gross="113", quantity="2"), row(2, 2, "3", "109", "0.09")], ORDERS, SALES
    )
    assert price["cny"] == D("40")
    assert price["quantity"] == 5


def test_parent_purchase_unit_mismatch_blocks_only_margin():
    rows = [row(quantity="15000", gross="113000")]
    rows[0]["parent_purchase_unit"] = "盒"
    result = declared_margin(CUSTOMS, rows, ORDERS, SALES)
    assert result["status"] == "unit_mismatch" and result["margin"] is None
    assert result["purchase"]["quantity"] == 15000
    assert result["purchase"]["usd"] is not None


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("quantity", None, "采购下单数量"),
        ("quantity", D("0"), "采购下单数量"),
        ("quantity", D("-1"), "采购下单数量"),
        ("amount", None, "采购含税金额"),
        ("amount", D("0"), "采购含税金额"),
        ("tax_rate", None, "税率"),
        ("tax_rate", D("-0.13"), "税率"),
    ],
)
def test_incomplete_purchase_row_never_falls_back_to_customs_price(field, value, reason):
    price = purchase_price(CUSTOMS, [{**row(), field: value}], ORDERS, SALES)
    assert price["usd"] is None and reason in price["note"]


@pytest.mark.parametrize(
    "sales,reason",
    [
        ({}, "未匹配"),
        ({9: {**SALES[9], "order_no": "OTHER"}}, "未匹配"),
        ({9: {**SALES[9], "exchange_rate": None}}, "汇率"),
        ({9: {**SALES[9], "exchange_rate": D("0")}}, "汇率"),
        ({9: {**SALES[9], "currency": "EUR"}}, "USD"),
    ],
)
def test_missing_or_wrong_sales_order_never_borrows_a_rate(sales, reason):
    price = purchase_price(CUSTOMS, [row()], ORDERS, sales)
    assert price["usd"] is None and reason in price["note"]


def test_ambiguous_sales_and_duplicate_purchase_members_are_rejected():
    orders = {**ORDERS, 2: {"sales_order_id": 10, "currency": "CNY"}}
    sales = {**SALES, 10: {**SALES[9], "id": 10}}
    assert "不唯一" in purchase_price(CUSTOMS, [row(), row(2, 2)], orders, sales)["note"]
    assert "重复" in purchase_price(CUSTOMS, [row(), row()], ORDERS, SALES)["note"]


def test_native_usd_purchase_and_verified_currency_basis():
    orders = {1: {**ORDERS[1], "currency": "USD"}}
    price = purchase_price(CUSTOMS, [row(quantity="1", gross="113")], orders, SALES)
    assert price["usd"] == D("100")
    orders[1]["currency"] = None
    assert purchase_price(CUSTOMS, [row()], orders, SALES)["usd"] is None
    verified = purchase_price(
        CUSTOMS,
        [row(quantity="1", gross="113")],
        orders,
        SALES,
        bases={1: {"allowed": True, "currency": "CNY"}},
    )
    assert verified["cny"] == D("100")


def test_ambiguous_line_binding_does_not_choose_last_or_repeat_whole_amount():
    links = [
        {"purchase_line_id": 1, "customs_line_id": 10},
        {"purchase_line_id": 1, "customs_line_id": 20},
        {"purchase_line_id": 2, "customs_line_id": 20},
        {"purchase_line_id": 2, "customs_line_id": 20},
    ]
    assert line_bindings({"links": links}) == {2: 20}


def test_saved_purchase_rows_feed_usd_fields_without_changing_invoice_basis(ns, engine):
    order = purchase(amounts=("68400", "38400"))
    for (_, source), quantity in zip(order[2], ("9000", "6000"), strict=True):
        source["custrecord_swc_subpo_item_qty"] = D(quantity)
        source["custrecord_swc_subpo_item_bgqty"] = D(quantity)
        source["custrecord_swc_subpo_item_bgunit"] = "个"
    data = deepcopy(bundle([order], [customs()]))
    data["sales_orders"]["90"]["exchangerate"] = "6.70"
    save(ns, engine, data)
    reader = DeclarationService(engine)
    content = reader.detail(reader.index(ns.settings.account, "")[0]["id"])
    first = content["customs_lines"][0]
    content["customs_lines"] = [{**first, **CUSTOMS, "id": first["id"], "sales_order_no": "SO1"}]
    content["customs_lines"][0]["declaration_name"] = "铝运动水壶"
    for link in content["links"]:
        if link["purchase_line_id"]:
            link["customs_line_id"] = first["id"]
    frozen = review_lines(content)
    shown = declaration(content, "pending", False, None, True, "").customsLines[0]
    assert shown.purchaseCount == 2 and shown.purchaseOrderQuantity == "15000"
    assert shown.originalPrice == shown.purchaseUnitPriceUsd == "0.940431"
    assert shown.originalUnitPriceCny == "6.300885"
    assert shown.declaredUnitPriceUsd == "1.06" and shown.margin == "11.28%"
    assert [(line["quantity"], line["amount"]) for line in frozen] == [
        (D("9000"), D("68400")),
        (D("6000"), D("38400")),
    ]
