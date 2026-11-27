"""客户名称格式变体：汇总、名单、明细与历史银行收汇归属须一致。"""

from datetime import date
from decimal import Decimal

import pytest
from backend.core.errors import ApiError
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.dao import bank_receipt_dao, batch_dao
from backend.modules.settlement.dto.bank_receipt_dto import BankReceiptImportRequest, BankReceiptQuery
from backend.modules.settlement.dto.batch_dto import BatchQuery, CandidateQuery
from backend.modules.settlement.dto.hk_receipt_dto import HkRegistrationPreview
from backend.modules.settlement.dto.hk_workbench_dto import HkWorkbenchQuery
from backend.modules.settlement.dto.ledger_dto import LedgerQuery
from backend.modules.settlement.dto.overview_dto import OverviewQuery
from backend.modules.settlement.dto.receivable_dto import ReceivableQuery
from backend.modules.settlement.policy import receivable_policy as rules
from backend.modules.settlement.policy.consignee_policy import consignee_key
from backend.modules.settlement.policy.declaration_detail_policy import direct_evidence
from backend.modules.settlement.policy.route_policy import DIRECT, HK_TRANSIT, hk_consignee_keys, route_of
from backend.modules.settlement.service.bank_receipt_service import BankReceiptService
from backend.modules.settlement.service.batch_service import BatchService
from backend.modules.settlement.service.candidate_service import CandidateService
from backend.modules.settlement.service.contract_party_reader import resolve
from backend.modules.settlement.service.declaration_detail_service import DeclarationDetailService
from backend.modules.settlement.service.document_reader import DocumentReader
from backend.modules.settlement.service.hk_receipt_service import HkReceiptService
from backend.modules.settlement.service.hk_workbench_service import HkWorkbenchService
from backend.modules.settlement.service.ledger_service import LedgerService
from backend.modules.settlement.service.overview_service import OverviewService
from backend.modules.settlement.service.receivable_service import ReceivableService
from backend.tests.settlement.test_bank_receipt_import import RECEIPT, payload
from backend.tests.settlement.test_settlement_batches import create
from backend.tests.settlement.test_settlement_ledger import add_receipt, receipt_row
from backend.tests.test_customs_receipts import _import
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns

NAME = "MECOLOUR DIGITAL TECHNOLOGY (HK) CO., LIMITED"
TOTAL = "127365.32"
TODAY = date(2026, 11, 27)
NUMBERS = [f"REAL{number}" for number in range(870, 874)]


@pytest.fixture
def customers(schema_engine, ns):
    save(
        ns,
        schema_engine,
        bundle(
            [purchase(str(200 + i), str(870 + i)) for i in range(4)],
            [customs(str(870 + i)) for i in range(4)],
        ),
    )
    _import(
        CustomsReceiptService(schema_engine),
        [
            receipt_row(number, NAME + ("." if i == 3 else ""), amount, f"2026-11-{7 + i:02}")
            for i, (number, amount) in enumerate(
                zip(NUMBERS, ("20000", "20000", "30978.40", "56386.92"), strict=True)
            )
        ],
    )
    return schema_engine


@pytest.mark.parametrize("listed", [NAME, NAME + "."])
def test_hk_list_ignores_symbols_and_spaces_but_preserves_letters_and_digits(listed):
    keys = hk_consignee_keys([listed])
    for name in (
        NAME,
        NAME + ".",
        "mecolour digital technology （hk） co.,limited．",
        "MECOLOUR-DIGITAL_TECHNOLOGY/HK CO + LIMITED",
    ):
        assert route_of("", name, keys)[0] == HK_TRANSIT
    for name in (NAME + " A", NAME.replace("(HK)", "(US)"), NAME + "2"):
        assert route_of("", name, keys)[0] == DIRECT
    assert route_of("巴西", NAME, keys)[0] == DIRECT


def test_customer_summary_and_drilldowns_include_both_spellings(customers):
    candidates = CandidateService(customers)
    receivables = ReceivableService(customers, candidates, DocumentReader(), today=lambda: TODAY)
    overview = OverviewService(customers, candidates, receivables)
    for name in ("", NAME, NAME + "."):
        result = receivables.query(ReceivableQuery(consignee=name))
        assert len(result.customers) == 1
        customer = result.customers[0]
        assert (customer.count, customer.amount, customer.outstandingAmount) == (4, TOTAL, TOTAL)
        assert {item.declarationNo for item in result.items} == set(NUMBERS)
        assert sum(stage.count for stage in customer.stages) == 4
        summary = overview.query(OverviewQuery(consignee=name))
        assert summary.total == 1
        assert (summary.items[0].declarationCount, summary.items[0].declaredTotal) == (4, TOTAL)
        old = candidates.query(CandidateQuery(consignee=name))
        assert len(old.consignees) == 1
        assert (old.consignees[0].count, old.consignees[0].amount) == (4, TOTAL)
        assert len(old.items) == 4


def test_historic_receipt_keys_share_customer_without_crossing_company_or_currency(customers):
    candidates = CandidateService(customers)
    with customers.connect() as connection:
        company = candidates.load(connection, limit=None)[0]["export_company"]
    # 保留旧规则写入的 customer_key（含句点）；无需迁移或重新导入流水。
    add_receipt(customers, "2026-11-20", NAME, NAME + ".", "150000", company=company)
    add_receipt(customers, "2026-11-20", NAME, NAME, "500", company="另一收款公司")
    add_receipt(customers, "2026-11-20", NAME, NAME, "100", company=company, currency="EUR")
    receivables = ReceivableService(customers, candidates, DocumentReader(), today=lambda: TODAY)
    result = receivables.query(ReceivableQuery(consignee=NAME + "."))
    customer = result.customers[0]
    assert (customer.receivedAmount, customer.outstandingAmount, customer.overpaidAmount) == (
        TOTAL,
        "0.00",
        "23134.68",
    )
    assert result.totals[0].overpaidAmount == "23134.68"
    ledger = LedgerService(customers, candidates).query(LedgerQuery(consignee=NAME + ".", byRecipient=True))
    assert len(ledger.groups) == 3
    grouped = {(group.receivingCompany, group.currency): group for group in ledger.groups}
    assert (grouped[company, "USD"].exportTotal, grouped[company, "USD"].receiptTotal) == (TOTAL, "150000.00")
    assert grouped["另一收款公司", "USD"].exportTotal == "0.00"
    assert grouped[company, "EUR"].exportTotal == "0.00"
    with customers.connect() as connection:
        rows, _, receipts, *_ = receivables.snapshot(connection)
    evidence, balance = direct_evidence(rows[0], rows, receipts)
    assert len(evidence) == 4 and balance == "-22634.68"
    assert all(row["receipts"] for row in evidence)
    overview = OverviewService(customers, candidates, receivables).query(OverviewQuery(consignee=NAME + "."))
    usd = next(row for row in overview.items if row.currency == "USD")
    assert (usd.declarationCount, usd.declaredTotal, usd.receivedTotal) == (4, TOTAL, "150500.00")


def test_currency_and_different_customer_remain_separate():
    def declaration(number, name, currency):
        return dict(
            declaration_no=number,
            consignee=name,
            currency=currency,
            export_company="我方公司",
            export_date=TODAY,
            amount=Decimal("100"),
        )

    rows = [
        declaration("A", NAME, "USD"),
        declaration("B", NAME + ".", "EUR"),
        declaration("C", NAME + "2", "USD"),
    ]
    receipts = [
        dict(
            customer_key=NAME.lower().replace(" ", "") + ".",
            currency="USD",
            receiving_company="我方公司",
            amount=Decimal("120"),
        )
    ]
    paid, overpaid = rules.direct_received(rows, receipts)
    assert paid == {"A": Decimal("100"), "B": Decimal(0), "C": Decimal(0)}
    assert list(overpaid.values()) == [Decimal("20")]


def test_merged_hk_customer_can_select_and_register_all_members(customers):
    candidates = CandidateService(customers, hk_consignees=[NAME])
    reader = DocumentReader()
    workbench = HkWorkbenchService(
        customers, candidates, reader, fee_alert=Decimal("50"), today=lambda: TODAY
    )
    for name in (NAME, NAME + "."):
        assert workbench.query(HkWorkbenchQuery(consignee=name)).pendingTotal == 4
        suggested = candidates.query(CandidateQuery(consignee=name, targetAmount=TOTAL))
        assert set(suggested.suggestion or []) == set(NUMBERS)
    batches = BatchService(customers, candidates, reader, fee_alert=Decimal("50"))
    batch = create(batches, NUMBERS, TOTAL)
    assert batch.declaredTotal == TOTAL
    for name in (NAME, NAME + "."):
        result = workbench.query(HkWorkbenchQuery(consignee=name))
        assert result.pendingTotal == 0 and result.batchTotal == 1


def test_match_key_retains_letters_and_digits_only():
    assert consignee_key(NAME) == "MECOLOURDIGITALTECHNOLOGYHKCOLIMITED"
    assert consignee_key("  a-b_c/d.e,（香港） １２３ &+ ") == "ABCDE香港123"
    assert consignee_key(None) == consignee_key(" .,-_() ") == ""
    assert not hk_consignee_keys([" .,-_() "])
    assert not rules.usable(dict(amount=Decimal("1"), currency_issue="", consignee=" .,-_() "))


def test_env_spelling_is_used_across_queries_and_registration_without_rewriting_sources(customers):
    label = "MeColour-Digital Technology / HK Co., Limited."
    candidates = CandidateService(customers, hk_consignees=[label, NAME])
    reader = DocumentReader()
    receivables = ReceivableService(customers, candidates, reader, today=lambda: TODAY)
    workbench = HkWorkbenchService(
        customers, candidates, reader, fee_alert=Decimal("50"), today=lambda: TODAY
    )
    batches = BatchService(customers, candidates, reader, fee_alert=Decimal("50"))
    registration = HkReceiptService(customers, candidates, batches, None, fee_alert=Decimal("50"))
    details = DeclarationDetailService(receivables, fee_alert=Decimal("50"))

    # 配置中的不同大小写、空格和符号须同时适用于筛选与展示，不依赖数据库排序。
    for query in (label, NAME, consignee_key(NAME)):
        result = receivables.query(ReceivableQuery(consignee=query))
        assert len(result.customers) == 1 and result.customers[0].consignee == label
        assert {item.consignee for item in result.items} == {label}
        old = candidates.query(CandidateQuery(consignee=query))
        assert len(old.items) == 4 and {item.consignee for item in old.items} == {label}
        assert old.consignees[0].consignee == label
        overview = OverviewService(customers, candidates, receivables).query(OverviewQuery(consignee=query))
        assert overview.total == 1 and overview.items[0].consignee == label
        assert {item.consignee for item in workbench.query(HkWorkbenchQuery(consignee=query)).pending} == {
            label
        }

    check = registration.preview(
        HkRegistrationPreview(declarationNos=NUMBERS, receivedAmount=TOTAL, receivedOn=TODAY)
    )
    assert check.submit.allowed and check.consignee == label
    assert {item.consignee for item in check.rows} == {label}
    assert details.get(NUMBERS[-1]).item.consignee == label
    add_receipt(customers, "2026-11-20", NAME, NAME + ".", "100")
    bank = BankReceiptService(customers, candidates).browse(BankReceiptQuery(customer=label))
    assert bank.total == 1 and bank.items[0].customerName == label
    assert BankReceiptService(customers, candidates).browse(BankReceiptQuery(customer="OTHER")).total == 0

    batch = create(batches, NUMBERS, TOTAL)
    assert batch.consignee == label and {item.consignee for item in batch.items} == {label}
    browsed = batches.browse(BatchQuery(consignee=label))
    assert browsed.total == 1 and browsed.items[0].consignee == label
    assert batches.browse(BatchQuery(consignee="OTHER")).total == 0
    work = workbench.query(HkWorkbenchQuery(consignee=label))
    assert work.batchTotal == 1 and work.batches[0].batch.consignee == label
    assert details.get(NUMBERS[-1]).batch.consignee == label
    with customers.connect() as connection:
        assert {row["consignee"] for row in candidates.load(connection, limit=None)} == {NAME, NAME + "."}
        assert batch_dao.get(connection, batch.id)["consignee"] in {NAME, NAME + "."}
        stored = bank_receipt_dao.all_receipts(connection)[0]
        assert stored["customer_name"] == NAME + "."
        assert stored["customer_key"] == (NAME + ".").lower().replace(" ", "")
    with customers.connect() as connection:
        assert candidates.display_names(connection).display_name("Other - Customer") == "Other - Customer"


def test_contract_buyer_matching_uses_customer_rule_and_rejects_ambiguous_profiles():
    facts = dict(
        receipts={"A": {"consignee": NAME}, "B": {"consignee": "MECOLOUR DIGITAL TECHNOLOGY HK CO LIMITED"}},
        refs={"A": [{}], "B": [{}]},
        declarants={"A": "我方公司", "B": "我方公司"},
        parties={NAME.lower().replace(" ", ""): {"id": 1}, "我方公司": {"id": 2}},
    )
    planned = [dict(contract_no="CONTRACT", declaration_nos=["A", "B"])]
    bindings, issues = resolve(None, [], planned, facts=facts)
    assert not issues and bindings["CONTRACT"]["buyer"]["id"] == 1
    facts["parties"][consignee_key(NAME)] = {"id": 3}
    bindings, issues = resolve(None, [], planned, facts=facts)
    assert bindings["CONTRACT"]["buyer"] is None
    assert any("多个买方合同抬头" in issue for issue in issues)


def test_reimport_customer_format_variants_does_not_duplicate_or_rewrite_receipt(schema_engine):
    candidates = CandidateService(schema_engine, hk_consignees=[NAME])
    service = BankReceiptService(schema_engine, candidates)

    def upload(name):
        row = [*RECEIPT[:2], name, *RECEIPT[3:]]
        return service.import_file(BankReceiptImportRequest(**payload(row)), "finance-user")

    assert upload(NAME).imported == 1
    retry = upload("mecolour-digital technology/hk co limited")
    assert (retry.imported, retry.duplicates) == (0, 1)
    with pytest.raises(ApiError, match="客户、付款人或金额冲突"):
        upload(NAME + "2")
    with schema_engine.connect() as connection:
        rows = bank_receipt_dao.all_receipts(connection)
    assert len(rows) == 1 and rows[0]["customer_name"] == NAME
