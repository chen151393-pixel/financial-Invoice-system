"""缺失母单引用必须经独立查询证实为空；保存原值并定位同组实际失败单据。"""

import json
from decimal import Decimal

import pytest
from backend.app import create_events
from backend.core.errors import ApiError
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.policy.ns_config import parse_config
from backend.modules.source.policy.parent_reference_policy import PARENT_FIELD
from backend.modules.source.public import DeclarationService
from backend.modules.source.service.parent_reference_service import verify_missing_parents
from backend.modules.source.service.storage_service import StorageService
from backend.tests.test_source_optional_sync import source as source
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_source_storage import rows
from backend.tests.test_sync_optimization import batch as batch
from backend.tests.test_sync_partial_save import page_result


def install_parent_query(ns, records):
    original = ns.relation_rows
    calls = []

    def query(kind, ids):
        if kind != "purchase_parent_links":
            return original(kind, ids)
        calls.append(list(ids))
        return [
            {"id": identity, "parent_state": "empty"}
            for identity in ids
            if PARENT_FIELD not in records[ns.settings.pl_lookup["purchase"]["type"], identity]
        ]

    ns.relation_rows = query
    return calls


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("kind", ["customs-declarations", "sub-purchase-orders"])
def test_verified_empty_parent_preserves_amount_and_manual_currency_workflow(source, engine, partial, kind):
    ns, page, _, records = source
    head = records[ns.settings.pl_lookup["purchase"]["type"], "200"]
    head.pop(PARENT_FIELD)
    calls = install_parent_query(ns, records)
    if kind == "sub-purchase-orders":
        page = {**page, "rows": [{"id": "200", "number": head["name"], "record": head}]}
    events = create_events()
    storage = StorageService(ns, engine, events)
    save = storage.sync_partial_page if partial else storage.sync_page
    result = save(kind, lambda: page)
    if partial:
        assert result["batch"]["status"] == "completed"
    assert calls == [["200"]]
    assert any("SUB-200" in message and "币种待核实" in message for message in result["storage"]["warnings"])
    order = rows(engine, "SELECT * FROM source_purchase_orders")[0]
    assert order["currency"] is None and order["parent_order_id"] is None
    assert order["currency_source"] == "unresolved" and order["parent_relation_status"] == "no_parent"
    assert Decimal(str(order["total_amount"])) == Decimal("120.50")
    lines = rows(engine, "SELECT amount,quantity FROM source_purchase_order_lines ORDER BY id")
    assert [Decimal(str(line["amount"])) for line in lines] == [Decimal("100.50"), Decimal("20")]
    assert all(Decimal(str(line["quantity"])) == Decimal("10") for line in lines)
    payload = rows(engine, "SELECT payload FROM source_raw_records WHERE id=:id", id=order["raw_record_id"])[
        0
    ]
    raw = json.loads(payload["payload"])
    assert PARENT_FIELD not in raw["record"] and raw["parentReferenceCheck"]["state"] == "empty"
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    review.approve(
        int(group.id),
        ApproveRequest(
            contentSha256=group.contentSha256,
            currencyEvidence=[
                {
                    "purchaseOrderId": str(order["id"]),
                    "currency": "CNY",
                    "reference": "测试合同",
                    "note": "人工核实",
                }
            ],
        ),
        "user:admin",
    )
    task_lines = rows(engine, "SELECT expected_amount FROM task_lines ORDER BY id")
    assert [Decimal(str(line["expected_amount"])) for line in task_lines] == [
        Decimal("100.50"),
        Decimal("20"),
    ]
    save(kind, lambda: page)
    assert calls == [["200"], ["200"]]
    assert review.browse(DeclarationListQuery()).groups[0].review.status == "approved"
    assert rows(engine, "SELECT currency FROM source_purchase_orders")[0]["currency"] is None
    assert len(rows(engine, "SELECT id FROM task_tasks")) == 1


def test_verified_no_parent_keeps_existing_unresolved_review_workflow(source, engine):
    ns, page, _, records = source
    records[ns.settings.pl_lookup["purchase"]["type"], "200"].pop(PARENT_FIELD)
    install_parent_query(ns, records)
    events = create_events()
    StorageService(ns, engine, events).sync_page("customs-declarations", lambda: page)
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    review.approve(int(group.id), ApproveRequest(contentSha256=group.contentSha256), "user:admin")
    tasks = rows(engine, "SELECT currency FROM task_tasks")
    assert len(tasks) == 1 and tasks[0]["currency"] is None
    assert [
        Decimal(str(line["expected_amount"]))
        for line in rows(engine, "SELECT expected_amount FROM task_lines ORDER BY id")
    ] == [Decimal("100.50"), Decimal("20")]


@pytest.mark.parametrize(
    "answer",
    [
        [],
        [{"id": "200"}],
        [{"id": "200", "parent_state": "present", "parent_id": "100"}],
        [{"id": "200", "parent_state": "empty", "parent_id": "100"}],
        [{"id": "200", "parent_state": "unknown"}],
        [{"id": "999", "parent_state": "empty"}],
        [{"id": "200", "parent_state": "empty"}] * 2,
    ],
)
def test_unproven_absence_does_not_replace_existing_complete_data(source, engine, answer):
    ns, page, _, records = source
    storage = StorageService(ns, engine)
    storage.sync_page("customs-declarations", lambda: page)
    before = rows(engine, "SELECT * FROM source_purchase_orders")
    records[ns.settings.pl_lookup["purchase"]["type"], "200"].pop(PARENT_FIELD)
    original = ns.relation_rows
    ns.relation_rows = lambda kind, ids: answer if kind == "purchase_parent_links" else original(kind, ids)
    with pytest.raises(ApiError):
        storage.sync_page("customs-declarations", lambda: page)
    assert rows(engine, "SELECT * FROM source_purchase_orders") == before


@pytest.mark.parametrize("status", [403, 502])
def test_verification_permission_or_network_failure_is_not_no_parent(source, engine, status):
    ns, page, _, records = source
    records[ns.settings.pl_lookup["purchase"]["type"], "200"].pop(PARENT_FIELD)

    def fail(kind, ids):
        assert kind == "purchase_parent_links"
        raise ApiError(status, "查询失败")

    ns.relation_rows = fail
    with pytest.raises(ApiError, match="200"):
        StorageService(ns, engine).sync_page("customs-declarations", lambda: page)
    assert not rows(engine, "SELECT id FROM source_purchase_orders")


def test_same_customs_group_saves_with_verified_no_parent_sibling(batch, engine):
    ns, _, records, _ = batch
    spec = ns.settings.pl_lookup["purchase"]
    records[spec["type"], "201"][spec["customs"]] = {"id": "870"}
    records[spec["type"], "201"].pop(PARENT_FIELD)
    calls = install_parent_query(ns, records)
    page = [{"id": "200", "record": records[spec["type"], "200"]}]
    result = StorageService(ns, engine).sync_partial_page("sub-purchase-orders", lambda: page_result(page))
    assert result["batch"]["counts"]["saved"] == 1 and calls == [["201"]]
    orders = rows(
        engine, "SELECT ns_internal_id,currency FROM source_purchase_orders ORDER BY ns_internal_id"
    )
    assert orders == [
        {"ns_internal_id": "200", "currency": "CNY"},
        {"ns_internal_id": "201", "currency": None},
    ]
    assert result["storage"]["purchase"]["created"] == 2


def test_error_identifies_actual_sibling_document_and_preserves_other_group(batch, engine):
    ns, _, records, _ = batch
    spec = ns.settings.pl_lookup["purchase"]
    records[spec["type"], "201"][spec["customs"]] = {"id": "870"}
    records[spec["type"], "201"].pop(PARENT_FIELD)
    install_parent_query(ns, records)
    line_spec = ns.settings.pl_lookup["purchase_line"]
    records[line_spec["type"], "2011"][line_spec["storage_fields"]["tax_inclusive_price"]] = "bad-price"
    page = [{"id": key, "record": records[spec["type"], key]} for key in ("200", "202")]
    result = StorageService(ns, engine).sync_partial_page("sub-purchase-orders", lambda: page_result(page))
    failed = next(item for item in result["batch"]["items"] if item["status"] == "failed")
    assert failed["id"] == "200"
    assert "子采购单 SUB-201（内部编号 201）" in failed["reason"] and "unit_price" in failed["reason"]
    assert "本关联组未保存" in failed["reason"]
    assert result["batch"]["counts"]["saved"] == 1
    assert [
        r["ns_internal_id"] for r in rows(engine, "SELECT ns_internal_id FROM source_purchase_orders")
    ] == ["202"]


def test_no_extra_query_for_present_parent_and_no_broad_mapping_exception(source, engine):
    ns, page, calls, records = source
    StorageService(ns, engine).sync_page("customs-declarations", lambda: page)
    assert "purchase_parent_links" not in calls
    spec = ns.settings.pl_lookup["purchase"]
    spec["storage_fields"]["parent_order_no"] = "custrecord_typo"
    records[spec["type"], "200"].pop(PARENT_FIELD)
    with pytest.raises(ApiError, match="SUB-200.*custrecord_typo"):
        StorageService(ns, engine).sync_page("customs-declarations", lambda: page)


def test_missing_parent_verification_batches_without_total_cap(ns):
    calls = []
    ns.relation_rows = lambda kind, ids: (
        calls.append((kind, list(ids))) or [{"id": identity, "parent_state": "empty"} for identity in ids]
    )
    bundle = {"purchases": [(str(i), {"name": f"SUB-{i}"}, []) for i in range(1, 302)], "warnings": []}
    result = verify_missing_parents(ns, bundle, parse_config(ns.settings), lambda *args: None)
    assert [len(ids) for _, ids in calls] == [300, 1]
    assert len(result) == len(bundle["warnings"]) == 301
