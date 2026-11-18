"""直接收汇明细（总账）与银行收汇明细：非香港中转按境外收货人、收款人和币种汇总，香港中转不进总账。"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from backend.core.names import normalize_name
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.dto.bank_receipt_dto import BankReceiptQuery
from backend.modules.settlement.dto.ledger_dto import LedgerQuery
from backend.modules.settlement.entity import settlement_bank_receipts
from backend.modules.settlement.policy.ledger_policy import build_groups, currency_totals
from backend.modules.settlement.service.bank_receipt_service import BankReceiptService
from backend.modules.settlement.service.candidate_service import CandidateService
from backend.modules.settlement.service.ledger_service import LedgerService
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import insert

HK = "HONGKONG VISION DIGITAL PRINTING CO., LIMITED"


def receipt_row(number, consignee, total, exported, item="01", currency="USD"):
    """海关回执一行：指定出口日期与币制。"""
    values = row(number, item, "墨水", "个", 10, consignee, total=total)
    values[2] = exported
    values[14] = currency
    return values


def add_receipt(engine, day, payer, customer, amount, company="上海毅鑫", currency="USD", reference=None):
    """直接写入一笔银行收汇，构造总账测试数据。"""
    now = datetime(2026, 11, 1)
    with engine.begin() as connection:
        connection.execute(
            insert(settlement_bank_receipts).values(
                receipt_date=date.fromisoformat(day),
                receiving_company=company,
                receiving_account="美金账户",
                payer_name=payer,
                payer_key=normalize_name(payer),
                customer_name=customer,
                customer_key=normalize_name(customer),
                currency=currency,
                amount=Decimal(amount),
                reference=reference,
                imported_by="finance-user",
                imported_at=now,
                created_at=now,
                updated_at=now,
            )
        )


@pytest.fixture
def seeded(schema_engine, ns):
    """ACME 两张直接收汇报关单、一张币制有问题的报关单，香港公司一张；收汇四笔。"""
    numbers = ("870", "871", "872", "873")
    save(
        ns,
        schema_engine,
        bundle(
            [purchase(str(200 + index), number) for index, number in enumerate(numbers)],
            [customs(number) for number in numbers],
        ),
    )
    _import(
        CustomsReceiptService(schema_engine),
        [
            receipt_row("REAL870", "ACME LTD", 500, "2026-10-01"),
            receipt_row("REAL871", "ACME LTD", 300, "2026-10-20"),
            receipt_row("REAL872", HK, 1000, "2026-10-05"),
            receipt_row("REAL873", "ACME LTD", 10, "2026-10-08", item="01"),
            receipt_row("REAL873", "ACME LTD", 20, "2026-10-08", item="02", currency="EUR"),
        ],
    )
    # 与出口同一天的收汇：先记出口再记收汇
    add_receipt(schema_engine, "2026-10-01", "ACME LTD", "ACME LTD", "200", reference="FT001")
    # 三方代付：付款人不同，实际客户名称大小写与空白不同也归到同一收货人
    add_receipt(
        schema_engine,
        "2026-10-25",
        "PAY AGENT LLC",
        "acme  ltd",
        "700",
        company="上海毅烁",
        reference="FT002",
    )
    # 香港公司汇回境内：不进总账
    add_receipt(schema_engine, "2026-10-26", HK, HK, "990", reference="FT003")
    # 没有出口的客户先收到款：单独成组，余额为负
    add_receipt(schema_engine, "2026-10-27", "BETA GMBH", "BETA GMBH", "50", reference="FT004")
    return schema_engine


def services(engine):
    candidates = CandidateService(engine)
    return LedgerService(engine, candidates), BankReceiptService(engine, candidates)


def test_period_uses_opening_difference_and_receiving_company(seeded):
    company = "申报主体"
    add_receipt(seeded, "2026-10-18", "ACME LTD", "ACME LTD", "700", company=company, reference="DIRECT-1")
    add_receipt(seeded, "2026-10-26", "ACME LTD", "ACME LTD", "200", company=company, reference="DIRECT-2")
    ledger, _ = services(seeded)
    query = LedgerQuery(receivingCompany=company, startDate="2026-10-18", endDate="2026-10-20")
    (group,) = ledger.query(query).groups
    assert (group.openingBalance, group.exportTotal, group.receiptTotal, group.balance) == (
        "500.00",
        "300.00",
        "700.00",
        "100.00",
    )
    assert [entry.sourceNo for entry in group.entries] == ["DIRECT-1", "REAL871"]
    assert [entry.balance for entry in group.entries] == ["-200.00", group.balance]


def test_ledger_orders_exports_before_receipts_on_same_day():
    def entry(kind, day, amount, order):
        return {
            "kind": kind,
            "key": "acme",
            "name": "ACME",
            "currency": "USD",
            "date": day,
            "amount": Decimal(amount),
            "company": "",
            "source_no": order,
            "payer": "",
            "third_party": False,
            "order": order,
        }

    groups = build_groups(
        [
            entry("receipt", date(2026, 2, 3), "60000", "r1"),
            entry("export", date(2026, 1, 15), "40000", "e2"),
            entry("export", date(2026, 1, 1), "50000", "e1"),
            entry("receipt", date(2026, 1, 15), "10000", "r0"),
            entry("export", None, "5", "e0"),
        ]
    )
    (group,) = groups
    # 缺出口日期的排最前；1 月 15 日先出口后收汇
    assert [e["source_no"] for e in group["entries"]] == ["e0", "e1", "e2", "r0", "r1"]
    assert [e["balance"] for e in group["entries"]] == list(
        map(Decimal, ["5", "50005", "90005", "80005", "20005"])
    )
    assert (group["status"], group["balance"]) == ("outstanding", Decimal("20005"))
    (total,) = currency_totals(groups)
    assert (total["outstanding"], total["overpaid"]) == (Decimal("20005"), Decimal(0))


def test_ledger_covers_only_direct_consignees(seeded):
    ledger, _ = services(seeded)
    result = ledger.query(LedgerQuery())
    assert [(g.consignee, g.currency, g.statusLabel) for g in result.groups] == [
        ("ACME LTD", "USD", "超收"),
        ("BETA GMBH", "USD", "超收"),
    ]
    acme, beta = result.groups
    assert [(e.kind, e.exportDate or e.receiptDate) for e in acme.entries] == [
        ("export", "2026-10-01"),
        ("receipt", "2026-10-01"),
        ("export", "2026-10-20"),
        ("receipt", "2026-10-25"),
    ]
    first, _, _, paid = acme.entries
    # 出口取海关回执的出口日期与成交总价，出口抬头取 NS 报关单申报主体
    assert (first.kindLabel, first.exportCompany, first.exportAmount, first.sourceNo) == (
        "出口",
        "申报主体",
        "500.00",
        "REAL870",
    )
    assert (first.receiptCompany, first.receiptDate, first.receiptAmount) == ("", "", "")
    assert (paid.receiptCompany, paid.receiptAmount, paid.sourceNo) == ("上海毅烁", "700.00", "FT002")
    assert (paid.thirdParty, paid.payerName, paid.exportAmount) == (True, "PAY AGENT LLC", "")
    assert (acme.exportTotal, acme.receiptTotal, acme.balance) == ("800.00", "900.00", "-100.00")
    assert (beta.exportTotal, beta.receiptTotal, beta.balance, beta.status) == (
        "0.00",
        "50.00",
        "-50.00",
        "overpaid",
    )

    (total,) = result.totals
    assert (total.exportTotal, total.receiptTotal, total.balance) == ("800.00", "950.00", "-150.00")
    assert (total.outstanding, total.overpaid) == ("0.00", "-150.00")
    assert (total.consigneeCount, total.exportCount, total.receiptCount) == (2, 2, 3)
    # 币制有问题的直接收汇报关单不计入，单独列出原因
    assert [(s.declarationNo, s.reason) for s in result.skipped] == [
        ("REAL873", "海关回执明细币制不一致或缺失")
    ]


def test_ledger_filters_and_pages_by_consignee(seeded):
    ledger, _ = services(seeded)
    assert [g.consignee for g in ledger.query(LedgerQuery(consignee="acme")).groups] == ["ACME LTD"]
    assert ledger.query(LedgerQuery(status="outstanding")).total == 0
    assert [g.consignee for g in ledger.query(LedgerQuery(company="毅烁")).groups] == ["ACME LTD"]
    second = ledger.query(LedgerQuery(page=2, pageSize=1))
    assert (second.total, second.page, [g.consignee for g in second.groups]) == (2, 2, ["BETA GMBH"])
    # 合计按筛选范围，不受分页影响；超出末页时回到最后一页
    assert second.totals[0].balance == "-150.00"
    assert ledger.query(LedgerQuery(page=9, pageSize=1)).page == 2


def test_outstanding_balance_when_receipts_fall_short(seeded):
    ledger, _ = services(seeded)
    add_receipt(seeded, "2026-10-28", "ACME LTD", "ACME LTD", "40", currency="EUR")
    groups = {(g.consignee, g.currency): g for g in ledger.query(LedgerQuery()).groups}
    # 不同币种分开记账
    assert groups[("ACME LTD", "EUR")].balance == "-40.00"
    assert groups[("ACME LTD", "USD")].balance == "-100.00"


def test_bank_receipts_mark_third_party_and_route(seeded):
    _, bank = services(seeded)
    result = bank.browse(BankReceiptQuery())
    assert result.total == 4 and [r.reference for r in result.items] == ["FT004", "FT003", "FT002", "FT001"]
    by_ref = {r.reference: r for r in result.items}
    agent = by_ref["FT002"]
    assert (agent.payerName, agent.customerName, agent.thirdParty) == ("PAY AGENT LLC", "acme  ltd", True)
    assert (agent.receivingCompany, agent.amount, agent.routeLabel) == ("上海毅烁", "700.00", "直接收汇")
    assert (by_ref["FT003"].route, by_ref["FT003"].thirdParty) == ("hk_transit", False)
    totals = {t.receivingCompany: t for t in result.totals}
    assert (totals["上海毅鑫"].count, totals["上海毅鑫"].amount) == (3, "1240.00")
    assert (totals["上海毅鑫"].thirdPartyCount, totals["上海毅鑫"].thirdPartyAmount) == (0, "0.00")
    assert (totals["上海毅烁"].thirdPartyCount, totals["上海毅烁"].thirdPartyAmount) == (1, "700.00")

    only = bank.browse(BankReceiptQuery(thirdParty="yes"))
    assert [r.reference for r in only.items] == ["FT002"] and len(only.totals) == 1
    assert bank.browse(BankReceiptQuery(thirdParty="no", customer="ACME")).total == 1
    ranged = bank.browse(
        BankReceiptQuery(receiptFrom="2026-10-26", receiptTo="2026-10-27", pageSize=1, page=5)
    )
    assert (ranged.total, ranged.page, len(ranged.items)) == (2, 2, 1)
    with pytest.raises(ValueError, match="收汇日期开始不能晚于结束"):
        BankReceiptQuery(receiptFrom="2026-10-27", receiptTo="2026-10-26")


def test_ledger_and_bank_routes_return_validated_models(seeded):
    from backend.core.dependencies import current_owner
    from backend.modules.settlement.controller import bank_receipt_controller, ledger_controller
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    ledger, bank = services(seeded)
    app = FastAPI()
    app.include_router(ledger_controller.create_router(ledger))
    app.include_router(bank_receipt_controller.create_router(bank))
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    client = TestClient(app)
    listed = client.post("/api/settlement/ledger/query", json={"status": "overpaid"})
    assert listed.status_code == 200 and listed.json()["total"] == 2
    receipts = client.post("/api/settlement/bank-receipts/query", json={"thirdParty": "yes"})
    assert receipts.status_code == 200 and receipts.json()["items"][0]["customerName"] == "acme  ltd"
    assert client.post("/api/settlement/ledger/query", json={"status": "unknown"}).status_code == 422
