"""人民币单价固定容差：边界、配置注入、计数与筛选，使用合成数据。"""

from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.modules.review.policy.margin_policy import declared_margin
from backend.tests.review_helpers import customs_prices
from backend.tests.test_source_storage import bundle, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用隔离库
from backend.tests.test_source_storage import ns as ns  # 共用合成来源
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "difference,status",
    [
        ("-0.1", "ok"),
        ("0", "ok"),
        ("0.0305", "ok"),
        ("0.099999", "ok"),
        ("0.10", "ok"),
        ("0.100001", "negative"),
    ],
)
def test_unit_price_tolerance_boundary(difference, status):
    difference = Decimal(difference)
    # 用大数量保留分级金额下的微小单价差，验证不能按显示精度放行。
    quantity = Decimal("1000000")
    declared = Decimal("237.8695")
    result = declared_margin(
        {
            "declared_unit": "片",
            "declared_quantity": quantity,
            "declared_unit_price": declared,
            "unit_price": None,
            "currency": "CNY",
            "sales_order_no": "SO1",
        },
        [
            {
                "id": 1,
                "unit": "片",
                "parent_purchase_unit": "片",
                "quantity": quantity,
                "tax_rate": Decimal(0),
                "declared_unit": "片",
                "declared_quantity": quantity,
                "amount": (declared + difference) * quantity,
                "purchase_order_id": 1,
            }
        ],
        {1: {"currency": "CNY", "sales_order_id": 9}},
        {9: {"id": 9, "order_no": "SO1", "currency": "USD", "exchange_rate": Decimal("6.71")}},
    )
    assert result["status"] == status
    assert result["original"] - result["declared"] == difference
    assert ("精度范围内一致" in result["note"]) == (0 < difference <= Decimal("0.10"))
    if difference == Decimal("0.0305"):
        assert result["margin"] == Decimal("-0.01")
        assert result["note"] == "精度范围内一致（人民币单价差额 0.0305 元，容差 0.10 元）"


@pytest.mark.parametrize("raw", ["-0.1", "NaN", "Infinity", "abc", "0.001"])
def test_invalid_tolerance_config_is_rejected(raw):
    with pytest.raises(ValueError, match="REVIEW_UNIT_PRICE_TOLERANCE_CNY"):
        load_settings({"REVIEW_UNIT_PRICE_TOLERANCE_CNY": raw})


def test_default_and_zero_tolerance_config():
    assert load_settings({}).review_unit_price_tolerance_cny == Decimal("0.10")
    assert load_settings({"REVIEW_UNIT_PRICE_TOLERANCE_CNY": "0"}).review_unit_price_tolerance_cny == 0


def test_purchase_cny_cost_is_not_multiplied_by_sales_rate_again():
    customs_row = {
        "unit_price": Decimal("9999"),
        "declared_unit_price": Decimal("2"),
        "currency": "USD",
        "sales_order_no": "SO1",
        "declared_unit": "个",
        "declared_quantity": Decimal("1"),
    }
    orders = {1: {"sales_order_id": 9, "currency": "CNY"}}
    sales = {9: {"id": 9, "order_no": "SO1", "currency": "USD", "exchange_rate": Decimal("2")}}
    children = [
        {
            "id": 1,
            "purchase_order_id": 1,
            "declared_unit": "个",
            "declared_quantity": Decimal("1"),
            "unit": "个",
            "parent_purchase_unit": "个",
            "quantity": Decimal("1"),
            "amount": Decimal("4.12"),
            "tax_rate": Decimal(0),
        }
    ]
    result = declared_margin(customs_row, children, orders, sales)
    assert result["original"] == Decimal("4.12") and result["declared"] == Decimal("4")
    assert result["purchase"]["usd"] == Decimal("2.06")
    assert result["margin"] == Decimal("-3.00") and result["status"] == "negative"


@pytest.mark.parametrize("tolerance,alert", [("0.10", False), ("0.05", True), ("0", True)])
def test_configured_tolerance_reaches_api_counts_and_filters(context, ns, engine, tolerance, alert):
    # 采购含税金额 121.475 元按 13% 还原未税 107.50 元，除以下单数量 10 为 10.75 元，差额恰好 0.10 元。
    order = purchase(amounts=("121.475", "20.00"))
    for _, record in order[2]:
        record["custrecord_swc_subpo_item_bgunit"] = "个"
        record["custrecord_swc_subpo_item_bgqty"] = Decimal("10")
    save(
        ns,
        engine,
        bundle([order], [customs_prices("870", original="12.1475", declared="10.65", currency="CNY")]),
    )
    context.settings.review_unit_price_tolerance_cny = load_settings(
        {"REVIEW_UNIT_PRICE_TOLERANCE_CNY": tolerance}
    ).review_unit_price_tolerance_cny
    app = create_app(context.settings, context.ns, engine)
    app.state.review_calculations.rebuild()
    with TestClient(app) as client:
        headers = {"Origin": context.settings.origin}
        assert (
            client.post(
                "/api/session",
                headers=headers,
                json={
                    "username": "admin",
                    "password": context.settings.admin_password,
                },
            ).status_code
            == 200
        )

        def query(status):
            response = client.post("/api/review/declarations/query", headers=headers, json={"status": status})
            assert response.status_code == 200
            return response.json()

        data = query("all")
        item = data["groups"][0]
        assert item["marginAlert"] is alert
        assert item["autoReview"]["eligible"] is not alert
        assert data["counts"]["marginAlert"] == int(alert)
        assert data["counts"]["autoApprovable"] == int(not alert)
        assert query("margin_alert")["total"] == int(alert)
        assert query("auto")["total"] == int(not alert)
        assert item["customsLines"][0]["margin"] == "-0.94%"
    assert rows(engine, "SELECT id FROM review_records") == []  # 预判不产生审核写入
