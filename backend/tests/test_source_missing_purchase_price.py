"""子采购含税单价缺失可保存；原始金额、审核依据与严格字段校验保持不变。"""

import json
from decimal import Decimal

import pytest
from backend.app import create_events
from backend.core.errors import ApiError
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.source.mapper.storage_mapper import project
from backend.modules.source.policy.ns_config import parse_config
from backend.modules.source.public import DeclarationService
from backend.modules.source.service.storage_service import StorageService
from backend.tests.review_helpers import MaterializedReviewService as ReviewService
from backend.tests.review_helpers import approve_customs
from backend.tests.test_source_optional_sync import source as source
from backend.tests.test_source_storage import declaration, rows
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns

PRICE_FIELD = "custrecord_swc_subpo_item_ratewithrate"
PURCHASE_TYPE = "customrecord_swc_subpo"
LINE_TYPE = "customrecord_swc_subpo_item"


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("kind", ["customs-declarations", "sub-purchase-orders"])
@pytest.mark.parametrize("read_mode", ["projected", "detail"])
def test_missing_price_saves_complete_group_and_preserves_review_amounts(
    source, engine, partial, kind, read_mode
):
    ns, page, _, records = source
    records[LINE_TYPE, "2001"].pop(PRICE_FIELD)
    if read_mode == "detail":
        # 未支持批量投影的映射仍可经 REST 明细通道保存，不只修复批量读取。
        ns.settings.pl_lookup["purchase_line"]["fields"]["name"] = "custrecord_swc_subpo_item_item"
    if kind == "sub-purchase-orders":
        head = records[PURCHASE_TYPE, "200"]
        page = {**page, "rows": [{"id": "200", "number": head["name"], "record": head}]}
    events = create_events()
    storage = StorageService(ns, engine, events)
    save = storage.sync_partial_page if partial else storage.sync_page
    result = save(kind, lambda: page)
    if partial:
        assert result["batch"]["counts"]["saved"] == 1
        assert result["batch"]["counts"]["failed"] == 0
    assert result["storage"]["customs"]["created"] == result["storage"]["purchase"]["created"] == 1
    assert any("子采购单 SUB-200 有 1 条明细缺少含税单价" in w for w in result["storage"]["warnings"])
    saved = rows(engine, "SELECT unit_price, quantity, amount FROM source_purchase_order_lines ORDER BY id")
    assert saved[0]["unit_price"] is None
    assert Decimal(str(saved[1]["unit_price"])) == Decimal("10.05")
    assert [Decimal(str(row["amount"])) for row in saved] == [Decimal("100.50"), Decimal("20")]
    assert all(Decimal(str(row["quantity"])) == Decimal("10") for row in saved)
    head = rows(engine, "SELECT total_amount, currency FROM source_purchase_orders")[0]
    assert Decimal(str(head["total_amount"])) == Decimal("120.50") and head["currency"] == "CNY"
    raw = rows(engine, f"SELECT payload FROM source_raw_records WHERE record_type = '{PURCHASE_TYPE}'")[0]
    assert PRICE_FIELD not in json.loads(raw["payload"])["lines"][0]["record"]
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    approve_customs(review, int(group.id))
    review.approve(int(group.id), ApproveRequest(contentSha256=group.contentSha256), "user:admin")
    tasks = rows(engine, "SELECT expected_amount, expected_quantity FROM task_lines ORDER BY id")
    assert [Decimal(str(row["expected_amount"])) for row in tasks] == [Decimal("100.50"), Decimal("20")]
    assert all(Decimal(str(row["expected_quantity"])) == Decimal("10") for row in tasks)
    before = declaration(engine)["content_sha256"]
    again = save(kind, lambda: page)
    assert again["storage"]["purchase"]["created"] == again["storage"]["customs"]["created"] == 0
    assert declaration(engine)["content_sha256"] == before
    assert review.browse(DeclarationListQuery()).groups[0].review.status == "approved"
    assert len(rows(engine, "SELECT id FROM task_tasks")) == 1


@pytest.mark.parametrize("value", ["missing", None, ""])
def test_refresh_clears_old_price_and_invalidates_old_review_without_rewriting_tasks(source, engine, value):
    ns, page, _, records = source
    events = create_events()
    storage = StorageService(ns, engine, events)
    storage.sync_page("customs-declarations", lambda: page)
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    approve_customs(review, int(group.id))
    review.approve(int(group.id), ApproveRequest(contentSha256=group.contentSha256), "user:admin")
    tasks = rows(engine, "SELECT expected_amount, expected_quantity FROM task_lines ORDER BY id")
    before = declaration(engine)["content_sha256"]
    if value == "missing":
        records[LINE_TYPE, "2001"].pop(PRICE_FIELD)
    else:
        records[LINE_TYPE, "2001"][PRICE_FIELD] = value
    result = storage.sync_page("customs-declarations", lambda: page)
    assert any("缺少含税单价" in warning for warning in result["storage"]["warnings"])
    assert (
        rows(engine, "SELECT unit_price FROM source_purchase_order_lines ORDER BY id")[0]["unit_price"]
        is None
    )
    assert declaration(engine)["content_sha256"] != before
    assert review.browse(DeclarationListQuery()).groups[0].review.status != "approved"
    assert rows(engine, "SELECT expected_amount, expected_quantity FROM task_lines ORDER BY id") == tasks


@pytest.mark.parametrize("mode", ["wrong_mapping", "other_record_type"])
def test_missing_price_exception_is_limited_to_known_ns_mapping(source, mode):
    ns, _, _, records = source
    spec = parse_config(ns.settings).purchase_line
    record = records[LINE_TYPE, "2001"]
    record.pop(PRICE_FIELD)
    if mode == "wrong_mapping":
        spec.storage_fields["tax_inclusive_price"] = "custrecord_typo"
    else:
        spec.type = "customrecord_other"
    with pytest.raises(ApiError, match="缺少已配置字段"):
        project(record, "purchase_line", spec)


@pytest.mark.parametrize("key", ["quantity", "amount", "unit_name"])
def test_missing_price_does_not_hide_missing_critical_fields_or_overwrite_existing_group(source, engine, key):
    ns, page, _, records = source
    storage = StorageService(ns, engine)
    storage.sync_page("customs-declarations", lambda: page)
    before = rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY id")
    spec = parse_config(ns.settings).purchase_line
    record = records[LINE_TYPE, "2001"]
    record.pop(PRICE_FIELD)
    record.pop(spec.storage_fields[key])
    result = storage.sync_partial_page("customs-declarations", lambda: page)
    assert result["batch"]["counts"]["failed"] == 1
    assert result["storage"]["savedAt"] is None
    assert rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY id") == before
