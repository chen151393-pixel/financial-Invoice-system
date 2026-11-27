"""名称档案：已有客户复用、首次客户新增、香港配置覆盖与事务一致性。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from alembic import command
from backend.app import create_events
from backend.manage import SCHEMA_INI, _config
from backend.modules.review.public import CustomsReceiptsSaved
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.dao import bank_receipt_dao, consignee_dao
from backend.modules.settlement.dto.bank_receipt_dto import BankReceiptImportRequest, BankReceiptQuery
from backend.modules.settlement.dto.batch_dto import CandidateQuery
from backend.modules.settlement.dto.ledger_dto import LedgerQuery
from backend.modules.settlement.dto.overview_dto import OverviewQuery
from backend.modules.settlement.dto.receivable_dto import ReceivableQuery
from backend.modules.settlement.entity import settlement_bank_receipts
from backend.modules.settlement.policy.consignee_policy import consignee_key
from backend.modules.settlement.service.bank_receipt_service import BankReceiptService
from backend.modules.settlement.service.candidate_service import CandidateService
from backend.modules.settlement.service.consignee_service import initialize, register
from backend.modules.settlement.service.document_reader import DocumentReader
from backend.modules.settlement.service.ledger_service import LedgerService
from backend.modules.settlement.service.overview_service import OverviewService
from backend.modules.settlement.service.receivable_service import ReceivableService
from backend.tests.settlement.test_bank_receipt_import import RECEIPT, payload
from backend.tests.settlement.test_consignee_identity import NAME, NUMBERS, TOTAL
from backend.tests.settlement.test_consignee_identity import customers as customers
from backend.tests.settlement.test_settlement_ledger import add_receipt, receipt_row
from backend.tests.test_customs_receipts import _import
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import inspect, update


def saved_names(engine):
    with engine.connect() as connection:
        return consignee_dao.names(connection)


def test_existing_direct_customer_keeps_one_name_across_filters_and_new_imports(customers):
    canonical = "MeColour-Digital Technology / HK Co Limited"
    candidates = CandidateService(customers)
    with customers.connect() as connection:
        company = candidates.load(connection, limit=None)[0]["export_company"]
    add_receipt(customers, "2026-11-20", "AGENT", canonical, "100", company=company)
    with customers.begin() as connection:
        connection.execute(update(settlement_bank_receipts).values(imported_at=datetime(2000, 1, 1)))
    initialize(customers)
    assert saved_names(customers) == {consignee_key(NAME): canonical}
    receivables = ReceivableService(customers, candidates, DocumentReader())
    for keyword in (NAME, NAME + ".", canonical, "MECOLOURDIGITALTECHNOLOGYHKCOLIMITED"):
        result = receivables.query(ReceivableQuery(consignee=keyword))
        assert len(result.customers) == 1
        assert (result.customers[0].consignee, result.customers[0].count, result.customers[0].amount) == (
            canonical,
            4,
            TOTAL,
        )
        assert {item.consignee for item in result.items} == {canonical}
        old = candidates.query(CandidateQuery(consignee=keyword))
        assert {item.consignee for item in old.items} == {canonical}
        overview = OverviewService(customers, candidates, receivables).query(OverviewQuery(consignee=keyword))
        assert overview.total == 1 and overview.items[0].consignee == canonical
        ledger = LedgerService(customers, candidates).query(LedgerQuery(consignee=keyword))
        assert ledger.total == 1 and ledger.groups[0].consignee == canonical
        bank = BankReceiptService(customers, candidates).browse(BankReceiptQuery(customer=keyword))
        assert bank.total == 1 and bank.items[0].customerName == canonical

    # 回执格式变化、出口日期重新排序、进程重新启动均不覆盖已有展示原名。
    _import(
        CustomsReceiptService(customers, events=create_events()),
        [receipt_row(NUMBERS[0], "MECOLOUR DIGITAL TECHNOLOGY HK CO LIMITED", "20000", "2026-12-01")],
    )
    initialize(customers)
    fresh = CandidateService(customers)
    assert fresh.query(CandidateQuery()).consignees[0].consignee == canonical
    assert saved_names(customers) == {consignee_key(NAME): canonical}


def test_new_customer_is_added_once_and_original_sources_remain(customers):
    initialize(customers)
    events = create_events()
    service = CustomsReceiptService(customers, events=events)
    first, alias = "NEW - Customer 2, Ltd.", "new customer 2 ltd"
    _import(service, [receipt_row(NUMBERS[0], first, "20000", "2026-11-08")])
    _import(service, [receipt_row(NUMBERS[1], alias, "20000", "2026-11-10")])
    assert saved_names(customers) == {consignee_key(NAME): NAME, consignee_key(first): first}
    candidates = CandidateService(customers)
    result = candidates.query(CandidateQuery(consignee=alias))
    assert result.total == 2 and {row.consignee for row in result.items} == {first}
    with customers.connect() as connection:
        source = candidates.load(connection, numbers=NUMBERS[:2], limit=None)
    assert {row["consignee"] for row in source} == {first, alias}

    bank = BankReceiptService(customers, candidates)
    body = BankReceiptImportRequest(**payload([*RECEIPT[:2], alias, *RECEIPT[3:]]))
    assert bank.import_file(body, "finance-user").imported == 1
    assert len(saved_names(customers)) == 2
    other = "Brand-New Customer 3"
    assert (
        bank.import_file(
            BankReceiptImportRequest(
                **payload([*RECEIPT[:2], other, *RECEIPT[3:6], "10:00:00", *RECEIPT[7:]])
            ),
            "finance-user",
        ).imported
        == 1
    )
    assert saved_names(customers)[consignee_key(other)] == other
    with customers.connect() as connection:
        assert bank_receipt_dao.all_receipts(connection)[0]["customer_name"] == alias


def test_hk_config_overrides_registry_without_rewriting_it(customers):
    initialize(customers)
    label = "Mecolour Digital Technology (HK) Co., Limited."
    result = CandidateService(customers, hk_consignees=[label]).query(CandidateQuery())
    assert {item.consignee for item in result.items} == {label}
    assert {item.route for item in result.items} == {"hk_transit"}
    assert saved_names(customers) == {consignee_key(NAME): NAME}
    assert CandidateService(customers).query(CandidateQuery()).consignees[0].consignee == NAME


def test_event_failure_rolls_back_receipt_and_new_customer(customers):
    initialize(customers)
    events = create_events()

    def fail(_connection, _event):
        raise RuntimeError("模拟后续订阅失败")

    events.subscribe(CustomsReceiptsSaved, fail)
    service = CustomsReceiptService(customers, events=events)
    with pytest.raises(RuntimeError, match="模拟后续订阅失败"):
        _import(service, [receipt_row(NUMBERS[0], "ROLLBACK CUSTOMER", "20000", "2026-11-08")])
    assert saved_names(customers) == {consignee_key(NAME): NAME}
    with customers.connect() as connection:
        assert CandidateService(customers).load(connection, numbers=[NUMBERS[0]])[0]["consignee"] == NAME


def test_0058_upgrade_and_initialization_preserve_existing_data(customers):
    config = _config(SCHEMA_INI, customers.url.render_as_string(hide_password=False))
    command.downgrade(config, "0057_review_customs_import_jobs")
    assert "settlement_consignees" not in inspect(customers).get_table_names()
    command.upgrade(config, "head")
    initialize(customers)
    initialize(customers)
    assert saved_names(customers) == {consignee_key(NAME): NAME}
    with pytest.raises(RuntimeError, match="客户名称已有数据"):
        command.downgrade(config, "0057_review_customs_import_jobs")
    assert len(CandidateService(customers).query(CandidateQuery()).items) == 4


def test_mysql_parallel_aliases_create_only_one_name(schema_engine):
    if schema_engine.dialect.name != "mysql":
        pytest.skip("并发唯一键需要专用 MySQL 验证")
    gate = Barrier(2)

    def save(name):
        with schema_engine.begin() as connection:
            gate.wait(timeout=10)
            register(connection, [name], datetime(2026, 11, 27))

    aliases = ("ACME - CO., LTD", "acme co ltd")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(save, name) for name in aliases]
        for result in results:
            result.result(timeout=30)
    names = saved_names(schema_engine)
    assert len(names) == 1 and names["ACMECOLTD"] in aliases
    with schema_engine.begin() as connection:
        register(connection, ["ACME_CO_LTD"], datetime(2026, 11, 28))
    assert saved_names(schema_engine) == names
