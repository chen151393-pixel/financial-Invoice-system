"""人民币单价固定容差：边界、配置注入、计数与筛选，使用合成数据。"""

from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.modules.review.policy.margin_policy import declared_margin
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
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
    result = declared_margin(
        {
            "declared_unit": "片",
            "declared_unit_price": Decimal("35.45"),
            "currency": "USD",
            "sales_order_no": "SO1",
        },
        [
            {
                "unit": "片",
                "amount": (Decimal("237.8695") + difference) * 60,
                "quantity": Decimal("60"),
                "purchase_order_id": 1,
            }
        ],
        {1: {"currency": "CNY", "sales_order_id": 9}},
        {9: {"id": 9, "order_no": "SO1", "currency": "USD", "exchange_rate": Decimal("6.71")}},
    )
    assert result["status"] == status
    assert result["purchase"] - result["declared"] == difference
    assert ("精度范围内一致" in result["note"]) == (0 < difference <= Decimal("0.10"))
    if difference == Decimal("0.0305"):
        assert result["margin"] == Decimal("-0.01")  # 保留真实幅度，不伪装成零
        assert result["note"] == "精度范围内一致（人民币单价差额 0.0305 元，容差 0.10 元）"


@pytest.mark.parametrize("raw", ["-0.1", "NaN", "Infinity", "abc", "0.001"])
def test_invalid_tolerance_config_is_rejected(raw):
    with pytest.raises(ValueError, match="REVIEW_UNIT_PRICE_TOLERANCE_CNY"):
        load_settings({"REVIEW_UNIT_PRICE_TOLERANCE_CNY": raw})


def test_default_and_zero_tolerance_config():
    assert load_settings({}).review_unit_price_tolerance_cny == Decimal("0.10")
    assert load_settings({"REVIEW_UNIT_PRICE_TOLERANCE_CNY": "0"}).review_unit_price_tolerance_cny == 0


@pytest.mark.parametrize("tolerance,alert", [("0.10", False), ("0.05", True), ("0", True)])
def test_configured_tolerance_reaches_api_counts_and_filters(context, ns, engine, tolerance, alert):
    # 10.65 元申报单价与 107.50 / 10 = 10.75 元采购单价，差额恰好 0.10 元。
    save(ns, engine, bundle([purchase(amounts=("107.50", "20.00"))], [customs("870")]))
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
