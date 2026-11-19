"""收汇总览：两条路径、首段到账去重、作废、手续费、精确金额与完整范围合计。"""

from datetime import datetime

import pytest
from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.modules.settlement.controller.overview_controller import create_router
from backend.modules.settlement.dao import batch_dao
from backend.modules.settlement.dto.batch_dto import CancelRequest
from backend.modules.settlement.dto.overview_dto import OverviewQuery
from backend.modules.settlement.service.overview_service import OverviewService
from backend.tests.settlement.test_settlement_batches import HK, create, legacy_direct_batch, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_ledger import add_receipt
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient


def overview(engine):
    candidates, _ = services(engine)
    return OverviewService(engine, candidates)


def test_first_hk_receipt_and_direct_bank_receipts_count_once(seeded):
    candidates, batches = services(seeded)
    batch = create(batches, ["REAL870"], "585", fee="15")
    add_receipt(seeded, "2026-11-10", "ACME LTD", "acme  ltd", "250")
    # 银行里的香港公司汇回、旧直接收汇批次都不能重复计入客户实收。
    add_receipt(seeded, "2026-11-11", HK, HK, "590")
    legacy_direct_batch(seeded)
    result = OverviewService(seeded, candidates).query(OverviewQuery())
    (total,) = result.totals
    assert (total.declaredTotal, total.receivedTotal, total.outstanding, total.receivedFee) == (
        "2000.50",
        "835.00",
        "1165.50",
        "15.00",
    )
    hk, direct = total.routes
    assert (hk.declaredTotal, hk.receivedTotal, hk.outstanding) == ("1000.50", "585.00", "415.50")
    assert (direct.declaredTotal, direct.receivedTotal, direct.outstanding) == ("1000.00", "250.00", "750.00")
    assert [(row.consignee, row.declarationCount) for row in result.items] == [(HK, 2), ("ACME LTD", 1)]
    # 资料已出、汇回结汇后，客户实收仍然只有首次到账，不随批次阶段累加。
    for status in ("documents_ready", "settled"):
        with seeded.begin() as connection:
            batch_dao.update_batch(
                connection, batch.id, {"status": status, "remitted_amount": "590"}, datetime(2026, 11, 12)
            )
        assert overview(seeded).query(OverviewQuery()).totals == result.totals


def test_cancelled_batch_excluded_and_replacement_counted_once(seeded):
    _, batches = services(seeded)
    old = create(batches, ["REAL870"], "585", fee="15")
    batches.cancel(old.id, CancelRequest(reason="登记错误，重建"), "finance-user")
    assert overview(seeded).query(OverviewQuery()).totals[0].receivedTotal == "0.00"
    create(batches, ["REAL870"], "600")
    total = overview(seeded).query(OverviewQuery()).totals[0]
    assert (total.receivedTotal, total.receivedFee, total.outstanding) == ("600.00", "0.00", "1400.50")


def test_currencies_overpayments_and_decimal_precision(seeded):
    add_receipt(seeded, "2026-11-10", "ACME LTD", "ACME LTD", "1250")
    add_receipt(seeded, "2026-11-11", "ACME LTD", "ACME LTD", "0.10", currency="EUR")
    add_receipt(seeded, "2026-11-12", "ACME LTD", "ACME LTD", "0.20", currency="EUR")
    result = overview(seeded).query(OverviewQuery())
    assert result.currencies == ["EUR", "USD"]
    by_currency = {row.currency: row for row in result.totals}
    assert (
        by_currency["EUR"].declaredTotal,
        by_currency["EUR"].receivedTotal,
        by_currency["EUR"].outstanding,
    ) == ("0.00", "0.30", "-0.30")
    assert by_currency["USD"].receivedTotal == "1250.00"
    acme = next(row for row in result.items if row.consignee == "ACME LTD" and row.currency == "USD")
    assert acme.outstanding == "-250.00"
    only = overview(seeded).query(OverviewQuery(currency="EUR"))
    assert len(only.totals) == 1 and only.totals[0].routes[0].receivedTotal == "0.00"


def test_filters_pagination_and_totals_cover_all_rows(seeded):
    add_receipt(seeded, "2026-11-10", "ACME LTD", "acme  ltd", "250")
    service = overview(seeded)
    result = service.query(OverviewQuery(pageSize=1, page=99))
    assert (result.total, result.page, len(result.items)) == (2, 2, 1)
    assert result.totals[0].declaredTotal == "2000.50"
    filtered = service.query(OverviewQuery(consignee=" acme ", currency="USD"))
    assert filtered.total == 1 and filtered.items[0].consignee == "ACME LTD"
    assert (filtered.totals[0].declaredTotal, filtered.totals[0].receivedTotal) == ("1000.00", "250.00")
    empty = service.query(OverviewQuery(consignee="找不到的客户"))
    assert empty.items == [] and empty.totals == [] and empty.page == 1


def test_invalid_declarations_reported_instead_of_becoming_zero(seeded, monkeypatch):
    candidates, _ = services(seeded)
    original = candidates.load

    def invalid(connection, **kwargs):
        rows = original(connection, **kwargs)
        rows[0] = {**rows[0], "amount": None, "currency_issue": "海关回执明细币制不一致或缺失"}
        return rows

    monkeypatch.setattr(candidates, "load", invalid)
    result = OverviewService(seeded, candidates).query(OverviewQuery())
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == "海关回执明细币制不一致或缺失"
    assert result.totals[0].declaredTotal != "2000.50"


def test_empty_database_and_unconfigured_database(schema_engine):
    result = overview(schema_engine).query(OverviewQuery())
    assert result.items == [] and result.totals == [] and result.currencies == []
    with pytest.raises(ApiError, match="业务数据库未配置"):
        overview(None).query(OverviewQuery())


def test_overview_http_validates_request_and_returns_money_strings(seeded):
    app = FastAPI()
    app.include_router(create_router(overview(seeded)))
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    client = TestClient(app)
    response = client.post("/api/settlement/overview/query", json={"consignee": "ACME"})
    assert response.status_code == 200
    assert response.json()["totals"][0]["declaredTotal"] == "1000.00"
    assert client.post("/api/settlement/overview/query", json={"pageSize": 0}).status_code == 422
    assert client.post("/api/settlement/overview/query", json={"receivedTotal": "999"}).status_code == 422
