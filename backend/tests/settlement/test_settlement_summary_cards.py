"""报关总应收与三个银行收款抬头卡片：完整范围、精度、筛选和零值。"""

from decimal import Decimal

from backend.modules.settlement.dto.bank_receipt_dto import BankReceiptQuery
from backend.modules.settlement.policy.receiving_company_policy import RECEIVING_COMPANIES
from backend.modules.settlement.service.bank_receipt_service import BankReceiptService
from backend.modules.settlement.service.candidate_service import CandidateService, _currency_totals
from backend.tests.settlement.test_settlement_ledger import add_receipt
from backend.tests.test_schema_baseline import schema_engine as schema_engine


def bank(engine):
    return BankReceiptService(engine, CandidateService(engine))


def test_receivable_totals_sum_original_decimals_and_separate_currencies():
    rows = [
        {"currency": "USD", "amount": Decimal("0.004"), "route": "direct"},
        {"currency": "USD", "amount": Decimal("0.004"), "route": "hk_transit"},
        {"currency": "EUR", "amount": Decimal("100.10"), "route": "direct"},
        {"currency": "EUR", "amount": None, "route": "direct"},
    ]
    assert [(t.currency, t.count, t.amount) for t in _currency_totals(rows)] == [
        ("EUR", 1, "100.10"),
        ("USD", 2, "0.01"),
    ]
    assert _currency_totals([]) == []


def test_three_receiving_companies_are_present_when_no_receipts(schema_engine):
    result = bank(schema_engine).browse(BankReceiptQuery())
    assert result.total == 0
    assert [(t.receivingCompany, t.currency, t.amount, t.featuredCompany) for t in result.totals] == [
        (name, "USD", "0.00", True) for name in RECEIVING_COMPANIES
    ]


def test_receiving_company_totals_do_not_group_by_payer_or_customer(schema_engine):
    first, second, third = RECEIVING_COMPANIES
    add_receipt(schema_engine, "2026-11-01", second, third, "100.10", company=first)
    add_receipt(schema_engine, "2026-11-02", "PAYER A", "CUSTOMER A", "0.20", company=f" {first} ")
    add_receipt(schema_engine, "2026-11-02", first, first, "300.00", company=third)
    # 同一前缀不能猜作相同法人主体，其他抬头仍保留。
    add_receipt(schema_engine, "2026-11-03", first, first, "50.00", company=f"{first}（其他）")
    service = bank(schema_engine)
    result = service.browse(BankReceiptQuery(pageSize=1))
    assert result.total == 4 and len(result.items) == 1
    known = {t.receivingCompany: t for t in result.totals if t.featuredCompany}
    assert list(known) == list(RECEIVING_COMPANIES)
    assert (known[first].count, known[first].amount, known[first].thirdPartyAmount) == (2, "100.30", "100.30")
    assert known[second].amount == "0.00" and known[third].amount == "300.00"
    assert [(t.receivingCompany, t.amount) for t in result.totals if not t.featuredCompany] == [
        (f"{first}（其他）", "50.00")
    ]
    filtered = service.browse(BankReceiptQuery(receiptFrom="2026-11-02", receiptTo="2026-11-02"))
    assert [(t.receivingCompany, t.amount) for t in filtered.totals] == [
        (first, "0.20"),
        (second, "0.00"),
        (third, "300.00"),
    ]
    assert service.browse(BankReceiptQuery(page=99, pageSize=1)).totals == result.totals


def test_receiving_company_currencies_never_mix(schema_engine):
    first = RECEIVING_COMPANIES[0]
    add_receipt(schema_engine, "2026-11-01", "A", "A", "100", company=first)
    add_receipt(schema_engine, "2026-11-01", "A", "A", "200", company=first, currency="EUR")
    result = bank(schema_engine).browse(BankReceiptQuery())
    assert len(result.totals) == 6
    amounts = {(t.receivingCompany, t.currency): t.amount for t in result.totals}
    assert amounts[(first, "USD")] == "100.00" and amounts[(first, "EUR")] == "200.00"
