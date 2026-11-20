"""总览：账龄完整范围、缺日期、手续费与超收、操作入口及分页。"""

from datetime import date
from decimal import Decimal

from backend.modules.settlement.dto.overview_dto import OverviewQuery
from backend.modules.settlement.policy.overview_insight_policy import customer_fields, describe
from backend.modules.settlement.service.overview_service import OverviewService
from backend.tests.settlement.test_settlement_batches import create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_ledger import add_receipt
from backend.tests.settlement.test_settlement_receivables import receivables
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns


def row(number, amount, days, stage="unpaid", route="direct", currency="USD", **extra):
    return dict(
        declaration_no=number,
        amount=Decimal(amount),
        received=Decimal(0),
        outstanding=Decimal(amount),
        aging=days,
        stage=stage,
        route=route,
        currency=currency,
        usable=True,
        consignee="ACME LTD",
        alert="",
        document=("unavailable", ""),
        batch=None,
        **extra,
    )


def group(declared="100", received="103", currency="USD"):
    return dict(
        route="direct",
        consignee="ACME LTD",
        currency=currency,
        declared=Decimal(declared),
        received=Decimal(received),
    )


def test_aging_includes_received_hk_but_excludes_settled_and_reports_missing_dates():
    rows = [
        row("a", "183000", 30),
        row("b", "227350", 60, "remit", "hk_transit"),
        row("c", "10.10", None),
        row("d", "305100", None, "settled"),
        row("e", "7.20", 91, currency="EUR"),
    ]
    eur, usd = describe(rows, [])
    assert eur["currency"] == "EUR" and eur["aging"][3]["amount"] == "7.20"
    assert [b["amount"] for b in usd["aging"]] == ["183000.00", "227350.00", "0.00", "0.00"]
    assert usd["unsettledAmount"] == "410360.10" and usd["unsettledCount"] == 3
    assert usd["unknownDateCount"] == 1
    assert usd["aging"][1]["barWidth"] == "100.00"
    assert usd["aging"][2]["barWidth"] == "0.00"


def test_customer_progress_uses_actual_cash_preserves_overpayment_and_oldest_stage():
    fields = customer_fields(group(), [row("a", "100", 37, "partial")])
    assert fields["receivedPercent"] == 100 and fields["receivedPercentText"] == "103%"
    assert fields["outstandingTone"] == "info"
    assert fields["oldestPendingText"] == "37 天 · 部分收汇"
    assert customer_fields(group(), [])["oldestPendingText"] == "— · 暂无报关单"


def test_actions_follow_real_state_prioritize_exceptions_and_keep_currency_separate():
    overdue = row("a", "52.15", 58, "remit", "hk_transit")
    overdue.update(alert="香港滞留 31 天", batch={"id": 1, "batch_no": "SB-1"})
    missing = row("b", "118.30", 35, "collected", "hk_transit")
    missing.update(document=("pending", "缺销售合同"), batch={"id": 2})
    rows = [
        overdue,
        missing,
        row("c", "113.30", 20, "unregistered", "hk_transit"),
        row("d", "105.80", 37, "partial"),
    ]
    (data,) = describe(rows, [group()], "ACME")
    assert [a["key"] for a in data["actions"]] == ["overdue", "overpaid", "register", "documents", "collect"]
    assert data["actions"][0]["batchNo"] == "SB-1"
    assert data["actions"][1]["amount"] == "-3.00"
    assert data["actions"][2]["target"] == "receipts"
    assert data["actions"][3]["stage"] == "collected"
    assert all(a["consignee"] == "ACME" for a in data["actions"])
    assert describe([], []) == []


def test_live_overview_snapshot_totals_and_insights_ignore_customer_pagination(seeded):
    candidates, batches = services(seeded)
    create(batches, ["REAL870"], "585", fee="15")
    add_receipt(seeded, "2026-11-10", "ACME LTD", "ACME LTD", "1250")
    view = OverviewService(seeded, candidates, receivables(seeded, date(2026, 12, 20)))
    first = view.query(OverviewQuery(pageSize=1))
    second = view.query(OverviewQuery(pageSize=1, page=2))
    assert first.insights == second.insights and first.totals == second.totals
    assert first.asOf == "2026-12-20"
    assert first.totals[0].receivedTotal == "1835.00"
    assert first.totals[0].receivedFee == "15.00"
    assert first.totals[0].settledAmount == "0.00"
    acme = second.items[0]
    assert acme.consignee == "ACME LTD" and acme.outstanding == "-250.00"
    assert acme.receivedPercent == 100 and acme.receivedPercentText == "125%"
    assert view.query(OverviewQuery(currency="EUR")).insights == []
