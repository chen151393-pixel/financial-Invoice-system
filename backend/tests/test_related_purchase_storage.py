"""在隔离 MySQL 验证母子采购快照关联、重复导入和整批回滚。"""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.modules.business import dao
from backend.modules.business.storage_service import StorageService
from backend.tests.test_business_migrations import migrated_engine as migrated_engine
from sqlalchemy import text


@pytest.fixture
def sample():
    mapping = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/netsuite-pl-lookup.json").read_text(encoding="utf-8")
    )
    customs = {
        "id": "70",
        "name": "CD70",
        "custrecord_swc_realno": "REAL70",
        "custrecord315": "2026-09-20",
        "custrecord_swc_piname": {"id": "17", "refName": "申报主体"},
    }
    customs_line = {source: None for source in mapping["customs_line"]["storage_fields"].values()}
    customs_line.update(
        id="71",
        custrecord_swc_relate_record={"id": "70"},
        custrecord_swc_packing_no={"id": "80"},
        custrecord_swc_company={"id": "3", "refName": "采购公司"},
        custrecord_swc_delare_name="测试货品",
        custrecord_swc_quantity="10",
        custrecord_swc_unit="19",
        custrecord_swc_delare_unit="34",
    )
    purchase = {
        "id": "90",
        "name": "PO90",
        "custrecord_swc_subpo_trandate": "2026-09-20",
        "custrecord_swc_subpo_mainpo": {"id": "100", "refName": "母单100"},
        "custrecord_swc_subpo_vendor": {"id": "8", "refName": "供应商"},
        "custrecord_swc_subpo_total": "123.45",
        "custrecord_swc_subpo_class": {"id": "3", "refName": "采购公司"},
        "custrecord_swc_subpo_plnum": {"id": "80"},
        "custrecord_swc_subpo_baoguannum": {"id": "70"},
    }
    line = {source: None for source in mapping["purchase_line"]["storage_fields"].values()}
    line.update(
        id="91",
        custrecord_swc_subpo_main={"id": "90"},
        custrecord_swc_subpo_item_lineid="1",
        custrecord_swc_subpo_item_qty="10",
        custrecord_swc_subpo_item_bgqty="5",
        custrecord_swc_subpo_item_bgunit="34",
        custrecord_swc_subpo_item_amountwithtax="123.45",
        custrecord_swc_subpo_item_item={"id": "777"},
        custrecord_swc_subpo_item_mainpo_lineid="7",
    )
    parent_line = {
        "line": 7,
        "item": {"id": "777", "refName": "测试货品"},
        "quantity": "20",
        "units": "19",
        "amount": "220",
        "tax1Amt": "26.90",
        "grossAmt": "246.90",
    }
    parent = {
        "id": "100",
        "tranId": "PARENT100",
        "tranDate": "2026-09-19",
        "entity": {"id": "8", "refName": "供应商"},
        "class": {"id": "3", "refName": "采购公司"},
        "currency": {"id": "1", "refName": "人民币"},
        "total": "246.90",
        "lastModifiedDate": "2026-09-20T01:00:00Z",
        "item": {"items": [parent_line], "totalResults": 1},
        "expense": {"items": [], "totalResults": 0},
    }
    bundle = {
        "source_account": "prod-test",
        "complete": True,
        "warnings": [],
        "pl_names": {"80": "PL80"},
        "customs": [("70", customs, [("71", customs_line)])],
        "purchases": [("90", purchase, [("91", line)])],
        "parents": [{"id": "100", "record": parent}],
        "unit_names": {"19": "瓶", "34": "千克"},
        "parent_line_evidence": [
            {
                "transaction": "100",
                "id": "7",
                "uniquekey": "7007",
                "mainline": "F",
                "taxline": "F",
                "item": "777",
                "quantity": "20",
                "units": "19",
                "foreignamount": "220",
            }
        ],
    }
    settings = Settings(
        account="prod-test",
        pl_lookup=mapping,
        record_types=[
            mapping[key]["type"] for key in ("pl", "purchase", "purchase_line", "customs", "customs_line")
        ],
    )
    return SimpleNamespace(settings=settings), bundle


def test_save_related_snapshot_repeat_links_units_and_source(migrated_engine, sample):
    ns, bundle = sample
    service = StorageService(ns, migrated_engine)
    owner = "related-" + uuid4().hex
    first = service.save_related_snapshot(bundle, owner)
    assert all(first[kind]["created"] == 1 for kind in ("parent", "purchase", "customs"))
    second = service.save_related_snapshot(bundle, owner)
    assert all(second[kind]["created"] == 0 for kind in ("parent", "purchase", "customs"))
    tenant, _ = service.scope(owner)
    with migrated_engine.connect() as c:
        row = (
            c.execute(
                text(
                    "SELECT p.parent_relation_status, l.ns_parent_line_ref, l.parent_purchase_order_line_id, m.id, m.source_line_key, l.unit_name, l.declaration_unit, m.unit_name AS parent_unit, m.amount FROM purchase_orders p JOIN purchase_order_lines l ON l.purchase_order_id=p.id JOIN parent_purchase_order_lines m ON m.id=l.parent_purchase_order_line_id WHERE p.tenant_id=:tenant"
                ),
                {"tenant": tenant},
            )
            .mappings()
            .one()
        )
        assert row["parent_relation_status"] == "linked"
        assert row["ns_parent_line_ref"] == "7"
        assert row["parent_purchase_order_line_id"] == row["id"]
        assert row["source_line_key"] == "transactionline:7007"
        assert row["unit_name"] is None
        assert row["declaration_unit"] == "千克"
        assert row["parent_unit"] == "瓶"
        assert str(row["amount"]) == "246.900000"


@pytest.mark.parametrize("problem", ["account", "partial", "parent_line", "item", "parent_count", "amount"])
def test_bad_related_snapshot_rejected_before_save(migrated_engine, sample, problem):
    ns, original = sample
    bundle = deepcopy(original)
    if problem == "account":
        bundle["source_account"] = "another-account"
    elif problem == "partial":
        bundle["complete"] = False
    elif problem == "parent_line":
        bundle["purchases"][0][2][0][1]["custrecord_swc_subpo_item_mainpo_lineid"] = "1"
    elif problem == "item":
        bundle["purchases"][0][2][0][1]["custrecord_swc_subpo_item_item"] = {"id": "999"}
    elif problem == "parent_count":
        bundle["parents"][0]["record"]["item"]["totalResults"] = 2
    else:
        bundle["parents"][0]["record"]["total"] = "100"
    service = StorageService(ns, migrated_engine)
    owner = "rejected-" + uuid4().hex
    with pytest.raises(ApiError):
        service.save_related_snapshot(bundle, owner)
    tenant, _ = service.scope(owner)
    with migrated_engine.connect() as c:
        assert (
            c.execute(
                text("SELECT COUNT(*) FROM parent_purchase_orders WHERE tenant_id=:tenant"),
                {"tenant": tenant},
            ).scalar_one()
            == 0
        )


def test_related_snapshot_rolls_back_parent_and_customs(migrated_engine, sample, monkeypatch):
    ns, bundle = sample
    service = StorageService(ns, migrated_engine)
    original = dao.save_document

    def fail_child(connection, table, *args):
        if table.name == "purchase_orders":
            raise ApiError(422, "子单保存故障注入")
        return original(connection, table, *args)

    monkeypatch.setattr(dao, "save_document", fail_child)
    owner = "rollback-" + uuid4().hex
    with pytest.raises(ApiError, match="故障注入"):
        service.save_related_snapshot(bundle, owner)
    tenant, _ = service.scope(owner)
    with migrated_engine.connect() as c:
        for table in (
            "parent_purchase_orders",
            "parent_purchase_order_lines",
            "customs_declarations",
            "customs_declaration_lines",
        ):
            assert (
                c.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id=:tenant"), {"tenant": tenant}
                ).scalar_one()
                == 0
            )


def without_parent(bundle):
    result = deepcopy(bundle)
    del result["purchases"][0][1]["custrecord_swc_subpo_mainpo"]
    del result["purchases"][0][2][0][1]["custrecord_swc_subpo_item_mainpo_lineid"]
    result["parents"] = []
    result["parent_line_evidence"] = []
    result["purchase_parent_evidence"] = [{"id": "90", "parent_relation_status": "no_parent"}]
    return result


def test_verified_no_parent_clears_previous_links_and_keeps_raw_source(migrated_engine, sample):
    ns, bundle = sample
    service = StorageService(ns, migrated_engine)
    owner = "no-parent-" + uuid4().hex
    service.save_related_snapshot(bundle, owner)
    result = service.save_related_snapshot(without_parent(bundle), owner)
    assert result["purchase"]["updated"] == 1
    tenant, _ = service.scope(owner)
    with migrated_engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT p.parent_relation_status,p.parent_purchase_order_id,p.source_data,l.parent_purchase_order_id AS line_parent,l.parent_purchase_order_line_id,l.ns_parent_line_ref FROM purchase_orders p JOIN purchase_order_lines l ON p.id=l.purchase_order_id WHERE p.tenant_id=:tenant"
                ),
                {"tenant": tenant},
            )
            .mappings()
            .one()
        )
        assert row["parent_relation_status"] == "no_parent"
        assert all(
            row[key] is None
            for key in (
                "parent_purchase_order_id",
                "line_parent",
                "parent_purchase_order_line_id",
                "ns_parent_line_ref",
            )
        )
        source = json.loads(row["source_data"])
        assert "custrecord_swc_subpo_mainpo" not in source["record"]
        assert source["parentRelationEvidence"]["parent_relation_status"] == "no_parent"


@pytest.mark.parametrize(
    "problem", ["missing_proof", "wrong_state", "wrong_parent", "line_ref", "duplicate_proof", "wrong_scope"]
)
def test_unverified_no_parent_is_rejected(migrated_engine, sample, problem):
    ns, original = sample
    bundle = without_parent(original)
    evidence = bundle["purchase_parent_evidence"]
    if problem == "missing_proof":
        del bundle["purchase_parent_evidence"]
    elif problem == "wrong_state":
        evidence[0]["parent_relation_status"] = "linked"
    elif problem == "wrong_parent":
        evidence[0]["custrecord_swc_subpo_mainpo"] = "100"
    elif problem == "line_ref":
        bundle["purchases"][0][2][0][1]["custrecord_swc_subpo_item_mainpo_lineid"] = "7"
    elif problem == "duplicate_proof":
        evidence.append(dict(evidence[0]))
    else:
        evidence[0]["id"] = "999"
    with pytest.raises(ApiError):
        StorageService(ns, migrated_engine).save_related_snapshot(bundle, "unverified-" + uuid4().hex)


@pytest.mark.parametrize("problem", [None, "missing_proof", "conflicting_value", "amount"])
def test_omitted_optional_field_requires_exact_evidence(migrated_engine, sample, problem):
    ns, original = sample
    bundle = deepcopy(original)
    record = bundle["customs"][0][1]
    del record["custrecord_swc_piname"]
    bundle["empty_field_evidence"] = [
        {"kind": "customs", "id": "70", "field": "custrecord_swc_piname", "is_empty": "T"}
    ]
    if problem == "missing_proof":
        del bundle["empty_field_evidence"]
    elif problem == "conflicting_value":
        record["custrecord_swc_piname"] = {"id": "17"}
    elif problem == "amount":
        bundle["empty_field_evidence"] = [
            {"kind": "customs_line", "id": "71", "field": "custrecord_swc_grossamount", "is_empty": "T"}
        ]
    service = StorageService(ns, migrated_engine)
    owner = "empty-field-" + uuid4().hex
    if problem:
        with pytest.raises(ApiError):
            service.save_related_snapshot(bundle, owner)
    else:
        service.save_related_snapshot(bundle, owner)
        tenant, _ = service.scope(owner)
        with migrated_engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT declarant_identifier,declarant_name,source_data FROM customs_declarations WHERE tenant_id=:tenant"
                    ),
                    {"tenant": tenant},
                )
                .mappings()
                .one()
            )
            assert row["declarant_identifier"] is None and row["declarant_name"] is None
            assert "custrecord_swc_piname" not in json.loads(row["source_data"])["record"]


@pytest.mark.parametrize("verified", [True, False])
def test_missing_source_amount_is_never_zero_or_matched(migrated_engine, sample, verified):
    ns, original = sample
    bundle = deepcopy(original)
    line = bundle["purchases"][0][2][0][1]
    del line["custrecord_swc_subpo_item_amountwithtax"]
    if verified:
        bundle["empty_field_evidence"] = [
            {
                "kind": "purchase_line",
                "id": "91",
                "field": "custrecord_swc_subpo_item_amountwithtax",
                "is_empty": "T",
            }
        ]
    service = StorageService(ns, migrated_engine)
    owner = "empty-amount-" + uuid4().hex
    if not verified:
        with pytest.raises(ApiError):
            service.save_related_snapshot(bundle, owner)
        return
    result = service.save_related_snapshot(bundle, owner)
    assert any("金额待核实" in warning for warning in result["warnings"])
    tenant, _ = service.scope(owner)
    with migrated_engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT p.source_data,l.amount FROM purchase_orders p JOIN purchase_order_lines l ON l.purchase_order_id=p.id WHERE p.tenant_id=:tenant"
                ),
                {"tenant": tenant},
            )
            .mappings()
            .one()
        )
        assert row["amount"] is None
        assert json.loads(row["source_data"])["amountValidation"]["status"] == "source_missing"
