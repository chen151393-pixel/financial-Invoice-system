"""真实MySQL上的PL保存验收；NS使用假数据，不向真实业务库写测试单据。"""

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from backend.core.database import make_business_engine
from backend.core.errors import ApiError
from backend.modules.business import dao
from backend.modules.business.entity import load_tables
from backend.modules.business.storage_mapper import database_value, project_storage, validate_storage_config
from backend.modules.business.storage_service import StorageService
from backend.modules.source.policy.ns_config import parse_config
from backend.tests.pl_fakes import LookupNS
from sqlalchemy import Column, Date, MetaData, Numeric, String, Table, select


def configured_ns():
    ns = LookupNS()
    ns.settings.account = "isolated-test-account"
    ns.index["purchase", "customs", "20"] = ["10", "11"]
    ns.data["pl", "1"] = {"name": "PL001"}
    config = ns.settings.pl_lookup
    config["company_record_type"] = "classification"
    config["purchase"]["storage_fields"] = {"order_no": "name"}
    config["purchase_line"]["storage_fields"] = {
        "declaration_name": "name",
        "quantity": "quantity",
        "unit_name": "unit",
        "amount": "amount",
    }
    config["customs"]["storage_fields"] = {"declaration_no": "number", "declaration_date": "date"}
    config["customs_line"]["storage_fields"] = {
        "declaration_name": "name",
        "specification": "spec",
        "origin_place": "origin",
        "quantity": "quantity",
        "unit_name": "unit",
    }
    ns.data["pl", "9"] = {"name": "PL009"}
    ns.data["customs", "20"]["date"] = "2025-10-31"
    for (kind, _), record in ns.data.items():
        if kind in ("purchase_line", "customs_line"):
            record.update(name="纸", quantity=Decimal("10400"), unit="套", spec="A4", origin="深圳")
    return ns


def test_missing_storage_mapping_stops_before_ns_access():
    ns = LookupNS()
    with pytest.raises(ApiError, match="company_record_type"):
        validate_storage_config(parse_config(ns.settings))
    ns.settings.pl_lookup["company_record_type"] = "classification"
    with pytest.raises(ApiError, match="缺少映射"):
        validate_storage_config(parse_config(ns.settings))
    assert ns.calls == []


def customs_projection(*, allow_omitted=False, nullable=True):
    ns = configured_ns()
    if allow_omitted:
        ns.settings.pl_lookup["customs"]["omitted_as_null"] = ["declaration_no", "declaration_date"]
    config = parse_config(ns.settings)
    validate_storage_config(config)
    table = Table(
        "customs_declarations",
        MetaData(),
        Column("declaration_no", String(150), nullable=nullable),
        Column("declaration_date", Date, nullable=nullable),
    )
    return config.customs, table


def test_omitted_customs_fields_require_explicit_configuration():
    spec, table = customs_projection()
    with pytest.raises(ApiError, match="缺少已配置字段"):
        project_storage({}, spec, table)
    assert project_storage({"number": None, "date": None}, spec, table) == {
        "declaration_no": None,
        "declaration_date": None,
    }


def test_verified_omitted_customs_fields_become_null():
    spec, table = customs_projection(allow_omitted=True)
    assert project_storage({"name": "CD000074"}, spec, table) == {
        "declaration_no": None,
        "declaration_date": None,
    }
    result = project_storage({"number": "REAL-001", "date": "2026-09-14"}, spec, table)
    assert result["declaration_no"] == "REAL-001"
    assert str(result["declaration_date"]) == "2026-09-14"
    with pytest.raises(ApiError, match="格式"):
        project_storage({"date": "not-a-date"}, spec, table)


def test_omitted_fields_cannot_override_database_not_null():
    spec, table = customs_projection(allow_omitted=True, nullable=False)
    with pytest.raises(ApiError, match="缺少已配置字段"):
        project_storage({}, spec, table)


@pytest.mark.parametrize("kind, targets", [("purchase", ["declaration_no"]), ("customs", ["amount"])])
def test_omitted_configuration_cannot_relax_other_fields(kind, targets):
    ns = configured_ns()
    ns.settings.pl_lookup[kind]["omitted_as_null"] = targets
    with pytest.raises(ApiError):
        validate_storage_config(parse_config(ns.settings))


def test_omitted_configuration_cannot_replace_required_mapping():
    ns = configured_ns()
    spec = ns.settings.pl_lookup["customs"]
    spec["omitted_as_null"] = ["declaration_date"]
    del spec["storage_fields"]["declaration_date"]
    with pytest.raises(ApiError, match="已配置映射"):
        validate_storage_config(parse_config(ns.settings))


def test_missing_purchase_amount_still_fails():
    spec = parse_config(configured_ns().settings).purchase_line
    table = Table("purchase_order_lines", MetaData(), Column("amount", Numeric(24, 6)))
    spec.storage_fields = {"amount": "amount"}
    with pytest.raises(ApiError, match="缺少已配置字段amount"):
        project_storage({}, spec, table)


@pytest.mark.parametrize("value", ["NaN", "1.0000001", "1000000000000000000", 1.1, True])
def test_rejects_lossy_money(value):
    with pytest.raises(ApiError):
        database_value(value, Column("amount", Numeric(24, 6)))


@pytest.fixture
def mysql_storage():
    url = os.getenv("PL_STORAGE_TEST_URL")
    if not url:
        pytest.skip("需要已完成业务迁移的独立MySQL库PL_STORAGE_TEST_URL，库名须以_pl_test结尾")
    engine = make_business_engine(url)
    assert engine.url.database.endswith("_pl_test"), "只允许独立PL测试库"
    ns = configured_ns()
    service = StorageService(ns, engine)
    owner = "test-" + uuid4().hex
    try:
        yield service, ns, owner
    finally:
        tenants = [service.scope(name)[0] for name in (owner, owner + "-other")]
        with engine.begin() as connection:
            tables = load_tables(connection, include_relations=True)
            for name in (
                "customs_reconciliation_results",
                "purchase_order_lines",
                "customs_declaration_lines",
                "purchase_orders",
                "customs_declarations",
            ):
                table = tables[name]
                connection.execute(table.delete().where(table.c.tenant_id.in_(tenants)))
        engine.dispose()


def test_mysql_repeat_keeps_ids_counts_exact_amount_and_other_pl(mysql_storage):
    service, ns, owner = mysql_storage
    first = service.sync("PL001", owner)
    assert first["purchase"] == {"created": 2, "updated": 0, "linesCreated": 2, "linesUpdated": 0}
    assert first["customs"] == {"created": 1, "updated": 0, "linesCreated": 3, "linesUpdated": 0}
    before = service.query("PL001", 1, owner)
    assert before["total"] == 4
    assert service.query("PL009", 1, owner)["total"] == 1
    second = service.sync("PL001", owner)
    assert second["purchase"] == {"created": 0, "updated": 2, "linesCreated": 0, "linesUpdated": 2}
    assert second["customs"] == {"created": 0, "updated": 1, "linesCreated": 0, "linesUpdated": 3}
    after = service.query("PL001", 1, owner)
    assert [(r["source"], r["id"]) for r in before["rows"]] == [(r["source"], r["id"]) for r in after["rows"]]
    assert any(r["values"]["amount"] == "22880.000001" for r in after["rows"])
    assert service.query("PL001", 1, owner + "-other")["total"] == 0
    service.sync("PL001", owner + "-other")
    assert service.query("PL001", 1, owner)["total"] == 4


def test_mysql_failed_read_and_failed_transaction_preserve_all_rows(mysql_storage, monkeypatch):
    service, ns, owner = mysql_storage
    service.sync("PL001", owner)
    ns.data["purchase_line", "100"]["amount"] = Decimal("2.22")
    record = ns.data.pop(("customs_line", "201"))
    with pytest.raises(KeyError):
        service.sync("PL001", owner)
    ns.data["customs_line", "201"] = record
    original = dao.save_document

    def fail_on_purchase(connection, table, *args):
        if table.name == "purchase_orders":
            raise ApiError(422, "故障注入")
        return original(connection, table, *args)

    ns.data["customs", "20"]["number"] = "CHANGED"
    monkeypatch.setattr(dao, "save_document", fail_on_purchase)
    with pytest.raises(ApiError, match="故障注入"):
        service.sync("PL001", owner)
    result = service.query("PL001", 1, owner)
    assert any(r["values"]["amount"] == "22880.000001" for r in result["rows"])
    assert all(r["values"]["declaration"] != "CHANGED" for r in result["rows"])
    monkeypatch.setattr(dao, "save_document", original)
    assert service.sync("PL001", owner)["purchase"]["created"] == 0


def test_mysql_removed_lines_inactive_and_source_snapshot_exact(mysql_storage):
    service, ns, owner = mysql_storage
    service.sync("PL001", owner)
    ns.index["purchase_line", "parent", "10"] = []
    service.sync("PL001", owner)
    assert service.query("PL001", 1, owner)["total"] == 3
    tenant, _ = service.scope(owner)
    with service.engine.connect() as connection:
        tables = load_tables(connection)
        line = tables["purchase_order_lines"]
        rows = connection.execute(select(line.c.is_active).where(line.c.tenant_id == tenant)).scalars().all()
        assert sorted(rows) == [0, 1]
    ns.index["purchase_line", "parent", "10"] = ["100"]
    result = service.sync("PL001", owner)
    assert result["purchase"]["linesCreated"] == 0


def test_mysql_account_lock_rejects_overlapping_pl_before_remote_reads(mysql_storage):
    service, ns, owner = mysql_storage
    from hashlib import sha256

    tenant, account = service.scope(owner)
    key = sha256(f"pl-save:{service.engine.url.database}:{tenant}:{account}".encode()).hexdigest()
    with service.engine.connect() as connection:
        assert dao.acquire_sync_lock(connection, key)
        connection.commit()
        try:
            with pytest.raises(ApiError, match="已有"):
                service.sync("PL001", owner)
            assert ns.calls == []
        finally:
            dao.release_sync_lock(connection, key)
            connection.commit()
    assert service.sync("PL001", owner)["purchase"]["created"] == 2
