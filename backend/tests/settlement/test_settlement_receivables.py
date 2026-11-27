"""报关应收汇逐单状态：香港批次冲抵、直接收汇先出口先冲抵推算、阶段、账龄、资料状态与汇总。"""

from datetime import date, datetime
from decimal import Decimal

from backend.core.dependencies import current_owner
from backend.modules.settlement.controller.receivable_controller import create_router
from backend.modules.settlement.dao import batch_dao
from backend.modules.settlement.dto.receivable_dto import ReceivableQuery
from backend.modules.settlement.policy import receivable_policy as rules
from backend.modules.settlement.service.document_reader import DocumentReader
from backend.modules.settlement.service.receivable_service import ReceivableService
from backend.tests.settlement.test_settlement_batches import HK, create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_ledger import add_receipt
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient

TODAY = date(2026, 12, 20)


def receivables(engine, today=TODAY):
    candidates, _ = services(engine)
    return ReceivableService(engine, candidates, DocumentReader(), today=lambda: today)


def by_number(result):
    return {item.declarationNo: item for item in result.items}


def declaration(number, amount, exported, company="上海毅鑫", consignee="ACME LTD", currency="USD"):
    return {
        "declaration_no": number,
        "consignee": consignee,
        "currency": currency,
        "export_company": company,
        "export_date": date.fromisoformat(exported),
        "amount": Decimal(amount),
    }


def bank(amount, company="上海毅鑫", customer="ACME LTD", currency="USD"):
    return {
        "customer_key": customer.lower().replace(" ", ""),
        "currency": currency,
        "receiving_company": company,
        "amount": Decimal(amount),
    }


def test_direct_receipts_cover_earliest_exports_per_receiving_company():
    rows = [
        declaration("B", "300", "2026-10-20"),
        declaration("A", "500", "2026-10-01"),
        declaration("C", "80", "2026-10-02", company="上海毅烁"),
    ]
    received, overpaid = rules.direct_received(
        rows, [bank("600"), bank("100", company="上海毅烁"), bank("40", customer="ONLY RECEIPT")]
    )
    # 先出口的 A 先收齐，B 收到余下的 100；毅烁的收汇只冲抵毅烁的出口
    assert received == {"A": Decimal("500"), "B": Decimal("100"), "C": Decimal("80")}
    assert overpaid == {
        ("ACMELTD", "USD", "上海毅烁"): Decimal("20"),
        ("ONLYRECEIPT", "USD", "上海毅鑫"): Decimal("40"),
    }


def test_hk_batch_receipt_and_fee_cover_items_by_export_date():
    batch = {"received_amount": Decimal("690"), "received_fee": Decimal("10")}
    items = [
        {"declaration_no": "2", "export_date": date(2026, 10, 9), "declared_amount": Decimal("400.5")},
        {"declaration_no": "1", "export_date": date(2026, 10, 1), "declared_amount": Decimal("600")},
    ]
    assert rules.hk_received(batch, items) == {"1": Decimal("600"), "2": Decimal("100")}


def test_received_percent_caps_bar_but_keeps_actual_text():
    assert rules.received_percent(Decimal("400"), Decimal("1000")) == (40, "40%")
    assert rules.received_percent(Decimal("1250"), Decimal("1000")) == (100, "125%")
    assert rules.received_percent(Decimal("1"), Decimal("3")) == (33, "33%")
    assert rules.received_percent(Decimal("0"), None) == (0, "—")


def test_stages_follow_batch_status_and_direct_collection():
    hk = {"route": "hk_transit", "amount": Decimal("100"), "currency_issue": "", "consignee": HK}
    direct = {**hk, "route": "direct", "consignee": "ACME"}
    assert rules.stage_of(hk, Decimal(0), None) == rules.UNREGISTERED
    assert rules.stage_of(hk, Decimal(100), "collected") == rules.COLLECTED
    assert rules.stage_of(hk, Decimal(100), "documents_ready") == rules.REMIT
    assert rules.stage_of(hk, Decimal(100), "settled") == rules.SETTLED
    assert rules.stage_of(direct, Decimal(0), None) == rules.UNPAID
    assert rules.stage_of(direct, Decimal("99.99"), None) == rules.PARTIAL
    assert rules.stage_of(direct, Decimal(100), None) == rules.SETTLED
    assert rules.stage_of({**direct, "currency_issue": "币制不一致"}, Decimal(0), None) == rules.ISSUE


def test_unregistered_and_unpaid_before_any_receipt(seeded):
    result = receivables(seeded).query(ReceivableQuery())
    rows = by_number(result)
    assert {number: row.stage for number, row in rows.items()} == {
        "REAL870": "unregistered",
        "REAL871": "unregistered",
        "REAL872": "unpaid",
    }
    assert rows["REAL870"].documentStatus == "after_batch"
    assert rows["REAL872"].documentStatus == "none"
    assert rows["REAL872"].receivedBasis.startswith("推算")
    assert rows["REAL870"].agingDays is not None
    combined, hk, direct = result.totals
    assert (combined.route, combined.amount, combined.receivedAmount, combined.outstandingAmount) == (
        "all",
        "2000.50",
        "0.00",
        "2000.50",
    )
    assert (hk.pendingCount, hk.pendingAmount) == (2, "1000.50")
    assert (direct.amount, direct.pendingCount) == ("1000.00", 0)
    hk_customer, acme = result.customers
    assert (hk_customer.consignee, hk_customer.pendingCount, hk_customer.outstandingAmount) == (
        HK,
        2,
        "1000.50",
    )
    assert hk_customer.documentNote == "2 票登记回款后办理"
    assert acme.documentNote == "留存 0/1 齐 · 不影响结汇"
    assert {s.stage: s.count for s in result.stages}["unregistered"] == 2


def test_hk_batch_and_direct_inference_feed_rows_and_customers(seeded):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "990.50", fee="10")
    company = by_number(receivables(seeded).query(ReceivableQuery()))["REAL872"].exportCompany
    add_receipt(seeded, "2026-11-12", "MIZUHARA K.K.", "ACME LTD", "400", company=company)
    # 收款抬头不同的收汇不冲抵这张报关单，计为超收
    add_receipt(seeded, "2026-11-13", "ACME LTD", "ACME LTD", "50", company="上海绎色数码科技有限公司")
    result = receivables(seeded).query(ReceivableQuery())
    rows = by_number(result)
    assert (rows["REAL870"].stage, rows["REAL870"].receivedAmount, rows["REAL870"].batchId) == (
        "collected",
        "600.00",
        batch.id,
    )
    assert rows["REAL871"].outstandingAmount == "0.00"
    # 批次还没有提单：资料未齐，原因来自资料清单
    assert rows["REAL870"].documentStatus == "pending" and rows["REAL870"].documentNote
    assert (rows["REAL872"].stage, rows["REAL872"].receivedAmount, rows["REAL872"].outstandingAmount) == (
        "partial",
        "400.00",
        "600.00",
    )
    hk_customer = next(c for c in result.customers if c.consignee == HK)
    acme = next(c for c in result.customers if c.consignee == "ACME LTD")
    assert (hk_customer.receivedAmount, hk_customer.batchedCount, hk_customer.documentIssueCount) == (
        "1000.50",
        2,
        2,
    )
    assert (acme.receivedAmount, acme.outstandingAmount, acme.overpaidAmount) == ("400.00", "600.00", "50.00")
    assert (acme.receivedPercent, acme.receivedPercentText) == (40, "40%")
    assert (rows["REAL872"].receivedPercent, rows["REAL870"].receivedPercentText) == (40, "100%")
    # 未收多的客户排在前面
    assert [c.consignee for c in result.customers] == ["ACME LTD", HK]
    combined = result.totals[0]
    assert (combined.receivedAmount, combined.outstandingAmount, combined.overpaidAmount) == (
        "1400.50",
        "600.00",
        "50.00",
    )


def test_stranded_hk_batch_alert_and_stage_filter_only_narrows_items(seeded):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870"], "600")
    with seeded.begin() as connection:
        batch_dao.update_batch(connection, batch.id, {"status": "documents_ready"}, datetime(2026, 11, 12))
    service = receivables(seeded)
    remit = by_number(service.query(ReceivableQuery()))["REAL870"]
    # 2026-11-10 到账，至 12-20 已 40 天
    assert (remit.stage, remit.documentStatus, remit.alert) == ("remit", "ready", "香港滞留 40 天")
    alert = service.query(ReceivableQuery(stage="alert"))
    assert [item.declarationNo for item in alert.items] == ["REAL870"]
    assert alert.total == 1 and len(alert.customers) == 2
    assert {s.stage: s.count for s in alert.stages}["alert"] == 1
    assert receivables(seeded, today=date(2026, 11, 20)).query(ReceivableQuery()).items[0].alert == ""


def test_filters_keep_inference_from_full_history(seeded):
    company = by_number(receivables(seeded).query(ReceivableQuery()))["REAL872"].exportCompany
    add_receipt(seeded, "2026-11-12", "ACME LTD", "ACME LTD", "1000", company=company)
    result = receivables(seeded).query(ReceivableQuery(route="direct", exportTo="2030-01-01"))
    assert [(i.declarationNo, i.stage) for i in result.items] == [("REAL872", "settled")]
    assert [t.route for t in result.totals] == ["all", "hk_transit", "direct"]
    assert result.totals[1].count == 0
    assert receivables(seeded).query(ReceivableQuery(consignee="找不到")).items == []


def test_receivable_route(seeded):
    app = FastAPI()
    app.include_router(create_router(receivables(seeded)))
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    response = TestClient(app).post("/api/settlement/receivables/query", json={"stage": "unpaid"})
    assert response.status_code == 200
    body = response.json()
    assert [item["declarationNo"] for item in body["items"]] == ["REAL872"]
    assert body["asOf"] == "2026-12-20"
    bad = TestClient(app).post(
        "/api/settlement/receivables/query", json={"exportFrom": "2026-12-01", "exportTo": "2026-11-01"}
    )
    assert bad.status_code == 422
