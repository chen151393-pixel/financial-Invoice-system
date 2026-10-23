"""工作台：真实业务链路、全量筛选导出、币种日期口径和只读认证。"""

from datetime import datetime, timedelta
from decimal import Decimal

from backend.app import create_app
from backend.core.config import load_settings
from backend.modules.invoice.entity import headers
from backend.modules.matching.dto.matching_dto import ConfirmBody
from backend.modules.matching.dto.workbench_dto import WorkbenchQuery
from backend.modules.matching.policy.workbench_reports import BUSINESS_ZONE, month_report, supplier_ranking
from backend.modules.matching.service.workbench_service import WorkbenchService
from backend.tests.documents_ready import complete_documents
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import ACCOUNT, bundle, customs, purchase, save
from backend.tests.test_task import USER, approve
from fastapi.testclient import TestClient
from sqlalchemy import update


def read(engine, **values):
    return WorkbenchService(engine).read(WorkbenchQuery(**values))


def test_empty_auth_validation_and_export(engine, env):
    app = create_app(load_settings(env), engine=engine)
    with TestClient(app) as client:
        auth = {"Authorization": "Bearer " + env["SERVICE_API_KEY"]}
        for suffix in ("query", "export"):
            path = "/api/matching/workbench/" + suffix
            assert client.post(path, json={}).status_code == 401
            assert client.post(path, json={"pageSize": 0}, headers=auth).status_code == 400
            assert client.post(path, json={"kind": "fake"}, headers=auth).status_code == 400
            result = client.post(path, json={}, headers=auth)
            assert result.status_code == 200, result.text
        result = read(engine)
        assert result.counts.all == 0 and result.items == []
        assert result.month.percent is None and result.trend == []


def test_review_to_task_to_receipt_and_version_review(engine, ns, world):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    save(ns, engine, bundle([], [customs("880")]))  # 未出库：无子采购单，拉取时跳过
    initial = read(engine)
    assert initial.counts.review == 1
    assert [row.title for row in initial.items] == ["CD870"]
    assert initial.items[0].statusLabel == "待财务核对"
    assert all(row.amount is None for row in initial.items)
    approve(world, "CD870")
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与工作台计数
    result = read(engine)
    assert (result.counts.review, result.counts.task) == (0, 1)
    assert Decimal(next(row.amount for row in result.items if row.kind == "task")) == Decimal("120.5")
    number = "26000000000000009901"
    import_invoices(world, [invoice(number, [INK, FLUID], remark="SUB-200")])
    result = read(engine)
    assert result.counts.matching == 1 and result.counts.reverify == 0
    found = proposals(world, invoice_id(engine, number))
    for row in found:
        world["allocations"].confirm(int(row.id), ConfirmBody(), USER)
    result = read(engine)
    assert result.counts.matching == result.counts.task == 0
    assert result.month.completed == 1
    assert Decimal(result.month.received[0].amount) == Decimal("120.5")
    import_invoices(world, [invoice(number, [INK, FLUID], remark="SUB-200 换版")])
    result = read(engine)
    assert result.counts.reverify == result.counts.matching == 1
    assert result.counts.task == 1 and result.month.completed == 0


def test_filters_pagination_and_full_export(engine, ns, world, reviewed):
    save(ns, engine, bundle([purchase("210", "890")], [customs("890")]))
    save(ns, engine, bundle([], [customs("880")]))
    service = WorkbenchService(engine)
    first = read(engine, pageSize=1)
    second = read(engine, pageSize=1, page=2)
    assert first.total == 2 and first.pages == 2 and first.items[0].key != second.items[0].key
    assert read(engine, pageSize=1, page=100).page == 2
    assert read(engine, account="missing").total == 0
    assert read(engine, account=ACCOUNT).total == 2
    filtered = read(engine, keyword="SUB-200", kind="task")
    assert filtered.total == 1 and filtered.counts.all == 2 and filtered.filteredCounts.all == 1
    assert read(engine, keyword="%_").total == 0
    exported = service.read(WorkbenchQuery(pageSize=1, page=2), export=True)
    assert exported["count"] == 2 and "CD870" in exported["content"] and "CD890" in exported["content"]
    assert "CD880" not in exported["content"]
    assert service.read(WorkbenchQuery(keyword="SUB-200"), export=True)["count"] == 1


def test_invoice_trend_normal_only_by_date_currency_and_global_scope(engine, world):
    today = datetime.now(BUSINESS_ZONE).date()
    import_invoices(world, [invoice(f"2600000000000000991{i}", [INK]) for i in range(4)])
    with engine.begin() as connection:
        connection.execute(update(headers).values(invoice_date=today))
        connection.execute(update(headers).where(headers.c.invoice_no.endswith("1")).values(currency="USD"))
        connection.execute(update(headers).where(headers.c.invoice_no.endswith("2")).values(status="void"))
        connection.execute(
            update(headers)
            .where(headers.c.invoice_no.endswith("3"))
            .values(invoice_date=today - timedelta(days=7))
        )
    data = read(
        engine,
        account="NO_NS_ACCOUNT",
        keyword="没有匹配",
        kind="task",
        trendStart=today - timedelta(days=6),
        trendEnd=today,
    )
    assert data.total == 0
    trend = {row.currency: row for row in data.trend}
    assert set(trend) == {"CNY", "USD"}
    for series in trend.values():
        assert len(series.points) == 1 and Decimal(series.points[-1].amount) == Decimal("100.5")
        assert series.points[-1].percent == "100.0"
        assert series.points[0].date == today.isoformat()


def test_month_uses_shanghai_boundary_not_completion_month():
    today = datetime(2026, 10, 19).date()
    base = {
        "created_at": datetime(2026, 9, 30, 16),
        "status": "completed",
        "currency": "CNY",
        "received": Decimal("0.1"),
    }
    report = month_report(
        [
            base,
            {**base, "created_at": datetime(2026, 9, 30, 15, 59)},
            {**base, "status": "awaiting_invoice", "currency": "USD", "received": Decimal("0.2")},
        ],
        today,
    )
    assert report["total"] == 2 and report["completed"] == 1 and report["percent"] == "50.0"
    assert report["received"] == [{"currency": "CNY", "amount": "0.1"}, {"currency": "USD", "amount": "0.2"}]


def test_ranking_does_not_mix_currencies_or_partial_unknown_totals():
    base = {
        "status": "documents_pending",
        "ns_account": "A",
        "supplier_id": 1,
        "supplier": "供应商",
        "currency": "CNY",
        "outstanding": Decimal("0.1"),
    }
    result, unknown = supplier_ranking(
        [
            base,
            {**base, "outstanding": Decimal("0.2")},
            {**base, "currency": "USD", "outstanding": Decimal("10")},
            {**base, "supplier_id": 2, "outstanding": None},
            {**base, "supplier_id": 2, "outstanding": Decimal("100")},
            {**base, "status": "completed", "outstanding": Decimal("1000")},
        ]
    )
    assert unknown == 1
    assert [(row["currency"], row["amount"]) for row in result] == [("CNY", "0.3"), ("USD", "10")]


def test_source_changes_return_to_review(engine, ns, world, reviewed):
    assert read(engine).counts.review == 0
    save(ns, engine, bundle([purchase(amounts=("200", "20"))], [customs("870")]))
    assert read(engine).counts.review == 1


def test_trend_preserves_unknown_and_negative_values():
    from backend.modules.matching.policy.workbench_reports import invoice_trend

    today = datetime(2026, 10, 19).date()
    result = invoice_trend(
        [
            {"date": today, "currency": "CNY", "amount": Decimal("-10.123456")},
            {"date": today - timedelta(days=1), "currency": "CNY", "amount": None},
        ],
        today,
    )[0]
    assert result["hasNegative"]
    assert result["points"][-1]["amount"] == "-10.123456"
    assert result["points"][-1]["negative"]
    assert result["points"][-2]["amount"] is None


def test_export_treats_external_names_as_text(engine, ns):
    from backend.modules.matching.service.workbench_service import export_csv

    save(ns, engine, bundle([purchase()], [customs("870")]))
    item = read(engine).items[0].model_copy(update={"party": ' =HYPERLINK("https://example.invalid")'})
    content = export_csv([item])["content"]
    assert "' =HYPERLINK" in content


def test_trend_defaults_to_current_month_and_custom_historical_range(engine, world):
    today = datetime.now(BUSINESS_ZONE).date()
    previous = today.replace(day=1) - timedelta(days=1)
    import_invoices(world, [invoice(f"2600000000000000888{i}", [INK]) for i in range(3)])
    with engine.begin() as connection:
        connection.execute(update(headers).values(invoice_date=previous))
        connection.execute(
            update(headers).where(headers.c.invoice_no.endswith("1")).values(invoice_date=today)
        )
        connection.execute(
            update(headers)
            .where(headers.c.invoice_no.endswith("2"))
            .values(invoice_date=today, status="void")
        )
    default = read(engine)
    assert (default.trendStart, default.trendEnd) == (today.replace(day=1).isoformat(), today.isoformat())
    assert len(default.trend[0].points) == 1
    assert Decimal(default.trend[0].points[-1].amount) == Decimal("100.50")
    custom = read(engine, trendStart=previous, trendEnd=today)
    assert len(custom.trend[0].points) == 2
    assert sum(Decimal(p.amount) for p in custom.trend[0].points) == Decimal("201.00")
    assert custom.counts == default.counts
    with engine.begin() as connection:
        connection.execute(update(headers).values(invoice_date=previous))
    historical_only = read(engine)
    assert historical_only.trend == []
    assert historical_only.latestInvoiceDate == previous.isoformat()
    assert read(engine, trendStart=previous, trendEnd=previous).trend


def test_invalid_trend_ranges_rejected_by_api(engine, env):
    app = create_app(load_settings(env), engine=engine)
    with TestClient(app) as client:
        auth = {"Authorization": "Bearer " + env["SERVICE_API_KEY"]}
        for payload in (
            {"trendStart": "2026-08-14"},
            {"trendStart": "2026-08-22", "trendEnd": "2026-08-14"},
            {"trendStart": "2026-01-01", "trendEnd": "2026-10-19"},
            {"trendStart": "invalid", "trendEnd": "2026-08-22"},
        ):
            assert client.post("/api/matching/workbench/query", json=payload, headers=auth).status_code == 400
        response = client.post(
            "/api/matching/workbench/query",
            json={"trendStart": "2026-08-14", "trendEnd": "2026-08-22"},
            headers=auth,
        )
        assert response.status_code == 200
        assert response.json()["trendStart"] == "2026-08-14"


def test_trend_only_includes_invoiced_dates_even_for_zero_amounts():
    from backend.modules.matching.policy.workbench_reports import invoice_trend

    end = datetime(2026, 8, 31).date()
    start = end.replace(day=1)
    result = invoice_trend(
        [
            {"date": end.replace(day=22), "currency": "CNY", "amount": Decimal("10.50")},
            {"date": end.replace(day=14), "currency": "CNY", "amount": Decimal("0.00")},
            {"date": end.replace(day=18), "currency": "USD", "amount": None},
            {"date": start - timedelta(days=1), "currency": "CNY", "amount": Decimal("99.00")},
        ],
        end,
        start,
    )
    assert [point["date"] for point in result[0]["points"]] == ["2026-08-14", "2026-08-22"]
    assert result[0]["points"][0]["amount"] == "0.00"
    assert result[0]["points"][1]["percent"] == "100.0"
    assert [point["date"] for point in result[1]["points"]] == ["2026-08-18"]
    assert result[1]["points"][0]["amount"] is None
