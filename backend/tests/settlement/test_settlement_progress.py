"""进度图统计口径、同币种刻度、收款推算复用与筛选。"""

from decimal import Decimal

from backend.core.dependencies import current_owner
from backend.modules.settlement.controller.receivable_controller import create_router
from backend.modules.settlement.dto.progress_dto import ProgressQuery
from backend.modules.settlement.dto.receivable_dto import ReceivableQuery
from backend.modules.settlement.policy.settlement_progress_policy import describe
from backend.tests.settlement.test_settlement_batches import create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_ledger import add_receipt
from backend.tests.settlement.test_settlement_receivables import receivables
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient


def chart_row(number, amount, stage, route="hk_transit", currency="USD", received="0", usable=True):
    value = Decimal(amount)
    return dict(
        declaration_no=number,
        amount=value,
        stage=stage,
        route=route,
        currency=currency,
        usable=usable,
        received=Decimal(received),
        outstanding=value - Decimal(received),
    )


def test_stages_are_exclusive_use_same_scale_and_separate_currencies():
    rows = [
        chart_row("1", "600", "collected"),
        chart_row("2", "400", "settled"),
        chart_row("3", "300", "partial", "direct", received="100"),
        chart_row("4", "50", "settled", "direct", "EUR", "50"),
        chart_row("5", "9999", "issue", usable=False),
    ]
    currencies, excluded = describe(rows)
    eur, usd = currencies
    assert excluded == 1 and eur["currency"] == "EUR" and usd["currency"] == "USD"
    assert usd["count"] == 3 and usd["amount"] == "1300.00"
    assert usd["settledAmount"] == "400.00" and usd["unsettledAmount"] == "900.00"
    assert usd["barMaximum"] == "600.00" and usd["settledPercentText"] == "30.8%"
    stages = [s for r in usd["routes"] for s in r["stages"]]
    assert sum(s["count"] for s in stages) == 3
    assert sum(Decimal(s["amount"]) for s in stages) == Decimal("1300")
    partial = usd["routes"][1]["stages"][1]
    assert partial["barWidth"] == "50.00" and partial["receivedAmount"] == "100.00"
    assert partial["outstandingAmount"] == "200.00" and "已收 100.00" in partial["note"]
    assert usd["routes"][0]["stages"][0]["select"]["allowed"] is False


def test_zero_and_empty_do_not_show_a_false_completed_percentage():
    result, excluded = describe([])
    assert result == [] and excluded == 0
    (result,), _ = describe([chart_row("0", "0", "unpaid", "direct")])
    assert result["settledPercent"] == "0.00" and result["barMaximum"] == "0.00"
    assert all(s["barWidth"] == "0.00" for r in result["routes"] for s in r["stages"])


def test_progress_reuses_receivable_state_and_full_filter_scope(seeded):
    view = receivables(seeded)
    _, batches = services(seeded)
    create(batches, ["REAL870"], "600")
    company = next(r.exportCompany for r in view.query(ReceivableQuery()).items if r.route == "direct")
    add_receipt(seeded, "2026-11-12", "THIRD PARTY", "ACME LTD", "400", company=company)
    result = view.progress(ProgressQuery())
    (usd,) = result.currencies
    assert usd.amount == "2000.50" and usd.count == 3
    assert usd.routes[0].stages[0].amount == "400.50"
    assert usd.routes[0].stages[1].amount == "600.00"
    partial = usd.routes[1].stages[1]
    assert (partial.amount, partial.receivedAmount, partial.outstandingAmount) == (
        "1000.00",
        "400.00",
        "600.00",
    )
    assert partial.barWidth == "100.00"
    acme = view.progress(ProgressQuery(consignee="ACME", currency="usd"))
    assert acme.currencies[0].amount == "1000.00" and acme.currencies[0].routes[0].count == 0
    assert view.progress(ProgressQuery(currency="EUR")).currencies == []
    assert view.query(ReceivableQuery(currency="EUR")).total == 0
    assert view.progress(ProgressQuery()) == result


def test_progress_endpoint_uses_settlement_permission_and_strict_input(seeded):
    app = FastAPI()
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    app.include_router(create_router(receivables(seeded)))
    with TestClient(app) as client:
        response = client.post("/api/settlement/receivables/progress", json={"currency": "USD"})
        assert response.status_code == 200 and response.json()["currencies"][0]["count"] == 3
        assert client.post("/api/settlement/receivables/progress", json={"page": 1}).status_code == 422
