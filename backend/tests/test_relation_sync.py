"""同步来源关系：只读范围、精度、缺失依据和原子入库。"""

import json
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from backend.core.config import Settings, load_settings
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import NetSuite
from backend.modules.business import dao, relation_dao
from backend.modules.business.entity import load_tables
from backend.modules.business.pl_reader import PlReader
from backend.modules.business.public import CustomsReconciliationSource
from backend.modules.business.relation_backfill_service import RelationBackfillService
from backend.modules.business.relation_entity import RELATION_TABLE
from backend.modules.business.relation_reader import (
    PACK_CUSTOMS,
    PACK_PL,
    PACK_SALES,
    PACK_SALES_LINE,
    RelationReader,
)
from backend.modules.business.relation_storage_mapper import relation_values
from backend.modules.business.storage_service import StorageService
from backend.modules.reconciliation.local_mapper import declarations
from backend.tests.test_business_migrations import migrated_engine as migrated_engine
from backend.tests.test_pl_storage import configured_ns
from backend.tests.test_reconciliation import source_result
from backend.tests.test_related_purchase_storage import sample as sample
from backend.tests.test_sync_storage import page
from sqlalchemy import select


@pytest.fixture
def sources(sample):
    ns, bundle = sample
    ns.settings.finance_source_script = "customscript_test"
    ns.settings.finance_source_deploy = "customdeploy_test"
    row = {
        "id": "700",
        "declarationId": "70",
        "plId": "80",
        "packingId": "800",
        "companyId": "3",
        "fulfillmentId": "900",
        "fulfillmentLine": "1",
        "itemId": "777",
        "name": "测试货品",
        "sourceQuantity": "10.000000000000001",
        "declarationQuantity": "2.5",
        "declarationUnitId": "18",
        "declarationModel": "测试型号",
        "parentPurchaseId": "100",
    }
    response = {
        "contractVersion": 1,
        "complete": True,
        "account": "prod-test",
        "declarations": [{"id": "70", "recordNumber": "CD70", "rows": [row]}],
    }
    datasets = {
        "packing_by_customs": [
            {
                "id": "800",
                PACK_CUSTOMS: "70",
                PACK_PL: "80",
                PACK_SALES: "200",
                PACK_SALES_LINE: "2",
                "quantity": Decimal("10.000000000000001"),
            }
        ],
        "packing_by_id": [],
        "purchase_links": [
            {
                "previousdoc": "200",
                "previousline": "2",
                "nextdoc": "100",
                "nextline": "7",
                "linktype": "SpecOrd",
            }
        ],
        "parent_lines": bundle["parent_line_evidence"],
    }
    calls = []
    ns.finance_source_query = lambda ids: deepcopy(response)

    def relation_rows(kind, ids):
        calls.append((kind, ids))
        return deepcopy(datasets[kind])

    ns.relation_rows = relation_rows
    ns.settings.pl_restlet_script = "customscript_test_pl"
    ns.settings.pl_restlet_deploy = "customdeploy_test_pl"
    comparison = source_result(ns.settings.account)
    group = comparison["groups"][0]
    group.update(declarationId="70", recordNumber=bundle["customs"][0][1]["name"])
    group["rows"][1]["cells"][5] = bundle["purchases"][0][1]["name"]

    def script_query(criteria):
        result = deepcopy(comparison)
        result["query"] = criteria
        return result

    ns.pl_script_query = script_query
    return SimpleNamespace(
        ns=ns,
        bundle=bundle,
        response=response,
        datasets=datasets,
        calls=calls,
        comparison=comparison,
    )


def test_sync_collects_original_references_without_product_guessing(sources):
    result = RelationReader(sources.ns).collect(sources.bundle)["70"]
    assert result["status"] == "collected"
    assert result["rawPackingLinks"] == [{"rawLineId": "700", "packingId": "800"}]
    assert result["packingLines"][0]["quantity"] == "10.000000000000001"
    assert result["childOrders"][0]["lines"][0]["parentLineRef"] == "7"
    assert result["childOrders"][0]["lines"][0]["itemId"] == "777"
    assert result["parentLines"][0]["uniquekey"] == "7007"
    assert "allocations" not in result
    sources.response["declarations"][0]["rows"][0]["packingId"] = ""
    partial = RelationReader(sources.ns).collect(sources.bundle)["70"]
    assert partial["status"] == "partial" and not partial["rawPackingLinks"]


def test_initial_sync_reads_evidence_and_reuses_explicit_ns_line_relations(sources):
    result = RelationReader(sources.ns).collect(sources.bundle, match=True)["70"]
    assert result["status"] == "matched"
    assert result["comparison"]["ready"] is True
    group = result["comparison"]["payload"]["group"]
    assert group["rows"][1]["customsRowId"] == group["rows"][0]["id"]
    assert group["rows"][1]["cells"][14] == "125.00"
    assert len(result["rawLines"]) == len(result["packingLines"]) == 1


@pytest.mark.parametrize("failure", ["config", "version", "account", "header", "count", "child"])
def test_initial_sync_refuses_missing_interface_or_mixed_snapshot(sources, failure):
    if failure == "config":
        sources.ns.settings.finance_source_script = ""
    elif failure == "version":
        sources.comparison["contractVersion"] = 2
    elif failure == "account":
        sources.comparison["account"] = "other"
    elif failure == "header":
        sources.comparison["groups"][0]["declarationId"] = "999"
    elif failure == "count":
        sources.comparison["groups"][0]["customsCount"] = 2
    else:
        sources.comparison["groups"][0]["rows"][1]["cells"][5] = "其他子采购单"
    with pytest.raises(ApiError):
        RelationReader(sources.ns).collect(sources.bundle, match=True)


def test_ambiguous_ns_source_is_retained_without_enabling_review(sources):
    sources.comparison["groups"][0]["rows"][1]["customsRowId"] = None
    result = RelationReader(sources.ns).collect(sources.bundle, match=True)["70"]
    assert result["status"] == "partial" and result["comparison"]["ready"] is False


def test_undeployed_original_reader_keeps_available_evidence_and_reports_partial(sources):
    sources.ns.settings.finance_source_script = ""
    sources.ns.finance_source_query = lambda ids: pytest.fail("未配置不能调用")
    result = RelationReader(sources.ns).collect(sources.bundle)["70"]
    assert result["status"] == "partial" and not result["rawLines"]
    assert len(result["packingLines"]) == len(result["purchaseLinks"]) == 1
    assert "尚未配置" in result["issues"][0]


@pytest.mark.parametrize(
    "problem", ["account", "missing", "duplicate", "parent", "packing_scope", "pl", "failed"]
)
def test_invalid_or_partial_sources_fail_instead_of_saving_success(sources, problem):
    if problem == "account":
        sources.response["account"] = "other-account"
    elif problem == "missing":
        sources.response["declarations"] = []
    elif problem == "duplicate":
        rows = sources.response["declarations"][0]["rows"]
        rows.append(deepcopy(rows[0]))
    elif problem == "parent":
        sources.response["declarations"][0]["rows"][0]["declarationId"] = "99"
    elif problem == "packing_scope":
        sources.datasets["packing_by_customs"][0][PACK_CUSTOMS] = "99"
    elif problem == "pl":
        sources.datasets["packing_by_customs"][0][PACK_PL] = "99"
    else:
        sources.response["complete"] = False
    with pytest.raises(ApiError):
        RelationReader(sources.ns).collect(sources.bundle)


def test_reverse_lookup_includes_siblings_and_rejects_changed_membership():
    ns = configured_ns()
    bundle = PlReader(ns).collect_records("sub-purchase-orders", page(ns, ids=("10",))["rows"])
    assert {entry[0] for entry in bundle["purchases"]} == {"10", "11"}
    assert ns.calls.count(("purchase", "11")) == 1
    ns.index["purchase", "customs", "20"] = ["11"]
    with pytest.raises(ApiError, match="引用发生变化"):
        PlReader(ns).collect_records("sub-purchase-orders", page(ns, ids=("10",))["rows"])


def test_relation_transport_is_bounded_exact_and_fixed_to_configured_account():
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.host == "test-account.suitetalk.api.netsuite.com"
        assert json.loads(request.content)["q"].startswith("SELECT * FROM customrecord_swc_packinglist")
        return httpx.Response(
            200, content='{"items":[{"id":"800","quantity":0.123456789012345678}],"hasMore":false}'
        )

    ns = NetSuite(Settings(account="test-account"), httpx.Client(transport=httpx.MockTransport(respond)))
    ns.token = lambda: "test"
    try:
        rows = ns.relation_rows("packing_by_customs", ["70"])
        assert rows[0]["quantity"] == Decimal("0.123456789012345678")
        for kind, ids in [
            ("arbitrary", ["70"]),
            ("packing_by_customs", ["70) OR 1=1"]),
            ("packing_by_customs", ["70", "70"]),
        ]:
            with pytest.raises(ApiError):
                ns.relation_rows(kind, ids)
        assert len(calls) == 1
    finally:
        ns.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"items": [{"id": "1"}], "hasMore": True},
        {"items": [{"id": "1"}, {"id": "1"}], "hasMore": False},
        {"items": [{}], "hasMore": False},
        {"items": [], "hasMore": "false"},
    ],
)
def test_relation_transport_rejects_truncation_and_duplicate_identity(payload):
    ns = NetSuite(
        Settings(account="test"),
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))),
    )
    ns.token = lambda: "test"
    try:
        with pytest.raises(ApiError):
            ns.relation_rows("packing_by_customs", ["70"])
    finally:
        ns.close()


def test_source_config_requires_pair_and_safe_script_ids(env):
    with pytest.raises(ValueError, match="同时"):
        load_settings({**env, "NETSUITE_FINANCE_SOURCE_SCRIPT": "customscript_source"})
    with pytest.raises(ValueError, match="编号"):
        load_settings({**env, "NETSUITE_FINANCE_SOURCE_SCRIPT": "https://other.invalid"})


def test_mysql_relation_backfill_preserves_documents_and_rolls_back(migrated_engine, sources, monkeypatch):
    owner = "backfill-test-" + uuid4().hex
    storage = StorageService(sources.ns, migrated_engine)
    storage.save_related_snapshot(sources.bundle, owner)
    storage.save_related_snapshot(sources.bundle, owner + "-other")
    tenant, account = storage.scope(owner)
    service = RelationBackfillService(sources.ns, migrated_engine)
    with migrated_engine.connect() as connection:
        tables = load_tables(connection, include_relations=True)

    def read_all():
        with migrated_engine.connect() as connection:
            return {
                name: [dict(r) for r in connection.execute(select(table).order_by(table.c.id)).mappings()]
                for name, table in tables.items()
            }

    before = read_all()
    result = service.run(["70"], owner)
    assert result["saved"] == 1 and result["partial"] == 1
    after = read_all()
    for name in tables:
        if name != RELATION_TABLE:
            assert after[name] == before[name]
    result_row = next(r for r in after[RELATION_TABLE] if r["tenant_id"] == tenant)
    previous = next(r for r in before[RELATION_TABLE] if r["tenant_id"] == tenant)
    assert result_row["mode"] == "evidence_backfill"
    assert result_row["id"] == previous["id"]
    assert result_row["created_at"] == previous["created_at"]
    assert [r for r in after[RELATION_TABLE] if r["tenant_id"] != tenant] == [
        r for r in before[RELATION_TABLE] if r["tenant_id"] != tenant
    ]
    assert service.run(["70"], owner)["saved"] == 1
    with pytest.raises(ApiError, match="不属于"):
        service.run(["70"], owner + "-missing")
    stable = read_all()
    original = relation_dao.save_result

    def fail(*args):
        original(*args)
        raise ApiError(409, "故障注入")

    monkeypatch.setattr(relation_dao, "save_result", fail)
    with pytest.raises(ApiError, match="故障注入"):
        service.run(["70"], owner)
    assert read_all() == stable
    monkeypatch.setattr(relation_dao, "save_result", original)
    real_lock = dao.lock_relation_backfill_sources

    def changed(*args):
        result = real_lock(*args)
        result["customs"][0]["source_data"]["changed"] = True
        return result

    monkeypatch.setattr(dao, "lock_relation_backfill_sources", changed)
    with pytest.raises(ApiError, match="快照变化"):
        service.run(["70"], owner)
    assert read_all() == stable


def test_mysql_finance_pagination_with_large_relation_json(migrated_engine, sources):
    owner = "large-relations-" + uuid4().hex
    tenant, account = StorageService(sources.ns, migrated_engine).scope(owner)
    with migrated_engine.begin() as connection:
        tables = load_tables(connection, include_relations=True)
        table = tables["customs_declarations"]
        for number in range(40):
            head = {
                "tenant_id": tenant,
                "ns_account": account,
                "ns_internal_id": str(1000 + number),
                "record_no": f"CD{number:06}",
                "is_active": True,
                "source_data": {},
            }
            identity = connection.execute(table.insert().values(**head)).inserted_primary_key[0]
            evidence = {
                "version": 1,
                "account": account,
                "declarationId": head["ns_internal_id"],
                "status": "partial",
                "rawLines": [],
                "packingLines": [],
                "issues": [],
                "sourcePayload": "x" * 64000,
            }
            relation_dao.save_result(
                connection, tables[RELATION_TABLE], relation_values({**head, "id": identity}, evidence)
            )
    source = CustomsReconciliationSource(migrated_engine)
    first = source.read(owner, keyword="", account=account, page=1, page_size=20, include_rows=True)
    second = source.read(owner, keyword="", account=account, page=2, page_size=20, include_rows=True)
    assert first["total"] == second["total"] == 40
    assert [h["record_no"] for h in first["heads"] + second["heads"]] == [
        f"CD{n:06}" for n in reversed(range(40))
    ]
    assert len(first["relations"]) == len(second["relations"]) == 20
    assert all("source_data" not in row for row in first["heads"])


@pytest.mark.parametrize("has_comparison", [True, False])
def test_mysql_child_moves_invalidate_previous_customs_without_touching_other_owner(
    migrated_engine, sources, has_comparison
):
    owner = "moved-relation-" + uuid4().hex
    bundle = deepcopy(sources.bundle)
    bundle["relation_evidence"] = RelationReader(sources.ns).collect(bundle, match=True)
    if not has_comparison:
        evidence = bundle["relation_evidence"]["70"]
        evidence.pop("comparison")
        evidence["status"] = "partial"
    storage = StorageService(sources.ns, migrated_engine)
    storage.save_related_snapshot(bundle, owner)
    storage.save_related_snapshot(bundle, owner + "-other")
    moved = deepcopy(sources.bundle)
    old_head, old_line = moved["customs"][0][1], moved["customs"][0][2][0][1]
    new_head = {**old_head, "id": "72", "name": "CD72"}
    new_line = {**old_line, "id": "73", "custrecord_swc_relate_record": {"id": "72"}}
    moved["customs"] = [("72", new_head, [("73", new_line)])]
    moved["purchases"][0][1][sources.ns.settings.pl_lookup["purchase"]["customs"]] = {"id": "72"}
    storage.save_related_snapshot(moved, owner)
    source = CustomsReconciliationSource(migrated_engine)
    criteria = {
        "keyword": "CD70",
        "account": sources.ns.settings.account,
        "page": 1,
        "page_size": 20,
        "include_rows": True,
    }
    changed = source.read(owner, **criteria)
    assert changed["counts"]["blocked"] == 0 and changed["counts"]["pending"] == 1
    assert declarations(changed)[0].purchaseCount == 0
    assert changed["relations"][changed["heads"][0]["id"]]["comparison"] is None
    with migrated_engine.connect() as connection:
        table = load_tables(connection, include_relations=True)[RELATION_TABLE]
        assert (
            connection.execute(
                select(table.c.mode).where(table.c.customs_declaration_id == changed["heads"][0]["id"])
            ).scalar_one()
            == "dependency_changed"
        )
    assert source.read(owner + "-other", **criteria)["counts"]["pending"] == 1


def test_mysql_sync_relations_atomic_repeat_missing_link_and_isolation(migrated_engine, sources, monkeypatch):
    ns, bundle = sources.ns, sources.bundle
    mapping = ns.settings.pl_lookup
    records = {
        (mapping[kind]["type"], identity): head
        for kind, items in (("customs", bundle["customs"]), ("purchase", bundle["purchases"]))
        for identity, head, _ in items
    }
    for kind, items in (("customs_line", bundle["customs"]), ("purchase_line", bundle["purchases"])):
        records.update(
            {(mapping[kind]["type"], identity): row for _, _, rows in items for identity, row in rows}
        )
    records[mapping["pl"]["type"], "80"] = {"name": "PL80"}
    index = {
        (mapping["purchase"]["type"], mapping["purchase"]["customs"], "70"): ["90"],
        (mapping["purchase_line"]["type"], mapping["purchase_line"]["parent"], "90"): ["91"],
        (mapping["customs_line"]["type"], mapping["customs_line"]["parent"], "70"): ["71"],
    }
    ns.validate = lambda kind, identity: None
    ns.request = lambda method, kind, identity, **kwargs: {"data": deepcopy(records[kind, identity])}
    ns.filtered_ids = lambda kind, field, value, **kwargs: list(index.get((kind, field, value), []))
    service = StorageService(ns, migrated_engine)
    owner = "relation-test-" + uuid4().hex
    tenant, account = service.scope(owner)

    def sync(identity=owner):
        return service.sync_page(
            "customs-declarations",
            lambda: {"rows": [{"id": "70", "record": deepcopy(bundle["customs"][0][1])}]},
            identity,
        )

    first = sync()
    assert first["storage"]["purchase"]["created"] == 1
    assert first["storage"]["relations"]["collected"] == 1
    assert first["storage"]["relations"]["matched"] == 1
    second = sync()
    assert second["storage"]["purchase"]["created"] == 0
    data = CustomsReconciliationSource(migrated_engine).read(
        owner, keyword="", account=account, page=1, page_size=20, include_rows=True
    )
    assert data["relations"][data["heads"][0]["id"]]["rawLines"] == 1
    assert declarations(data)[0].review.allowed is False
    assert declarations(data)[0].review.status == "pending"
    assert not declarations(data)[0].unlinkedLines
    assert declarations(data)[0].customsLines[0].purchaseLines[0].amount == "125.00"
    assert data["counts"]["pending"] == 1 and data["counts"]["blocked"] == 0
    comparison = data["relations"][data["heads"][0]["id"]]["comparison"]
    approved_data = CustomsReconciliationSource(migrated_engine).read(
        owner,
        keyword="",
        account=account,
        page=1,
        page_size=20,
        include_rows=True,
        status="approved",
        approved=[{"account": account, "declaration_id": "70", "digest": comparison["digest"]}],
    )
    assert approved_data["total"] == approved_data["counts"]["approved"] == 1
    sync(owner + "-other")
    with migrated_engine.connect() as connection:
        tables = load_tables(connection, include_relations=True)
        head = tables["customs_declarations"]
        original = connection.execute(
            select(head.c.source_data).where(head.c.tenant_id == tenant)
        ).scalar_one()
        assert "relationEvidence" not in original
        result_table = tables[RELATION_TABLE]
        saved_relation = dict(
            connection.execute(select(result_table).where(result_table.c.tenant_id == tenant))
            .mappings()
            .one()
        )
        assert saved_relation["evidence_data"]["rawLines"][0]["sourceQuantity"] == "10.000000000000001"
    sources.ns.settings.finance_source_script = ""
    with pytest.raises(ApiError, match="完整同步需要"):
        sync()
    sources.ns.settings.finance_source_script = "customscript_test"
    sources.comparison["contractVersion"] = 2
    with pytest.raises(ApiError, match="旧版"):
        sync()
    sources.comparison["contractVersion"] = 3
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(select(head.c.source_data).where(head.c.tenant_id == tenant)).scalar_one()
            == original
        )
        assert (
            dict(
                connection.execute(select(result_table).where(result_table.c.tenant_id == tenant))
                .mappings()
                .one()
            )
            == saved_relation
        )
    original_save = dao.save_document

    def fail(connection, table, *args):
        if table.name == "purchase_orders":
            raise ApiError(422, "故障注入")
        return original_save(connection, table, *args)

    monkeypatch.setattr(dao, "save_document", fail)
    with pytest.raises(ApiError, match="故障注入"):
        sync()
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(select(head.c.source_data).where(head.c.tenant_id == tenant)).scalar_one()
            == original
        )
        assert (
            dict(
                connection.execute(select(result_table).where(result_table.c.tenant_id == tenant))
                .mappings()
                .one()
            )
            == saved_relation
        )
    monkeypatch.setattr(dao, "save_document", original_save)
    index[mapping["purchase"]["type"], mapping["purchase"]["customs"], "70"] = []
    sources.comparison["groups"][0]["rows"] = sources.comparison["groups"][0]["rows"][:1]
    sources.comparison["groups"][0]["purchaseCount"] = 0
    sources.comparison["counts"]["purchase"] = 0
    sync()
    after_removal = CustomsReconciliationSource(migrated_engine).read(
        owner,
        keyword="",
        account=account,
        page=1,
        page_size=20,
        include_rows=True,
    )
    assert after_removal["counts"]["blocked"] == 0 and after_removal["counts"]["pending"] == 1
    assert declarations(after_removal)[0].customsLines[0].purchaseLines == []
    with migrated_engine.connect() as connection:
        purchase = tables["purchase_orders"]
        assert (
            connection.execute(
                select(purchase.c.customs_declaration_id).where(purchase.c.tenant_id == tenant)
            ).scalar_one()
            is None
        )
        other = service.scope(owner + "-other")[0]
        assert (
            connection.execute(
                select(purchase.c.customs_declaration_id).where(purchase.c.tenant_id == other)
            ).scalar_one()
            is not None
        )
