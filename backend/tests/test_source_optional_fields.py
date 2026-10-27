"""报关型号未返回可按未知保存；其他缺失、错误映射和格式错误仍拒绝整批。"""

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
from backend.tests.test_source_optional_sync import source as source
from backend.tests.test_source_storage import declaration, rows
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns


def test_missing_customs_model_keeps_full_save_review_and_task_chain(source, engine):
    ns, page, _, records = source
    spec = ns.settings.pl_lookup["customs_line"]
    records[spec["type"], "8701"].pop("custrecord_swc_huge")
    events = create_events()
    storage = StorageService(ns, engine, events)
    result = storage.sync_page("customs-declarations", lambda: page)["storage"]
    assert result["customs"]["linesCreated"] == result["purchase"]["linesCreated"] == 2
    assert any("1 条明细未返回规格型号" in message for message in result["warnings"])
    models = rows(engine, "SELECT specification FROM source_customs_lines ORDER BY source_line_key")
    assert [row["specification"] for row in models] == [None, "型号"]
    original = rows(
        engine, "SELECT payload FROM source_raw_records WHERE record_type = 'customrecord_swc_declare_record'"
    )[0]["payload"]
    assert "custrecord_swc_huge" not in json.loads(original)["lines"][0]["record"]
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    review.approve(int(group.id), ApproveRequest(contentSha256=group.contentSha256), "user:admin")
    amounts = rows(engine, "SELECT expected_amount FROM task_lines ORDER BY id")
    assert [Decimal(str(row["expected_amount"])) for row in amounts] == [Decimal("100.50"), Decimal("20")]
    assert rows(engine, "SELECT currency FROM source_purchase_orders")[0]["currency"] == "CNY"
    repeated = storage.sync_page("customs-declarations", lambda: page)["storage"]
    assert repeated["customs"]["created"] == repeated["purchase"]["created"] == 0
    assert len(rows(engine, "SELECT id FROM task_tasks")) == 1
    assert review.browse(DeclarationListQuery()).groups[0].review.status == "approved"


def test_missing_model_replaces_old_model_and_changes_digest(source, engine):
    ns, page, _, records = source
    storage = StorageService(ns, engine, create_events())
    storage.sync_page("customs-declarations", lambda: page)
    before = declaration(engine)["content_sha256"]
    spec = ns.settings.pl_lookup["customs_line"]
    records[spec["type"], "8701"].pop("custrecord_swc_huge")
    storage.sync_page("customs-declarations", lambda: page)
    assert declaration(engine)["content_sha256"] != before
    assert (
        rows(engine, "SELECT specification FROM source_customs_lines ORDER BY source_line_key")[0][
            "specification"
        ]
        is None
    )


@pytest.mark.parametrize("key", ["declaration_name", "quantity", "unit_name", "amount"])
def test_other_missing_fields_still_reject_entire_batch(source, engine, key):
    ns, page, _, records = source
    spec = ns.settings.pl_lookup["customs_line"]
    records[spec["type"], "8701"].pop(spec["storage_fields"][key])
    with pytest.raises(ApiError, match="缺少已配置字段"):
        StorageService(ns, engine).sync_page("customs-declarations", lambda: page)
    assert rows(engine, "SELECT id FROM source_customs_declarations") == []
    assert rows(engine, "SELECT id FROM source_purchase_orders") == []


@pytest.mark.parametrize("mode", ["wrong_mapping", "other_record_type", "oversized"])
def test_model_exception_cannot_mask_wrong_mapping_or_bad_value(source, mode):
    ns, _, _, records = source
    spec = parse_config(ns.settings).customs_line
    record = records[spec.type, "8701"]
    record.pop("custrecord_swc_huge")
    if mode == "wrong_mapping":
        spec.storage_fields["specification"] = "custrecord_typo"
    elif mode == "other_record_type":
        spec.type = "customrecord_other"
    else:
        record["custrecord_swc_huge"] = "型" * 501
    with pytest.raises(ApiError):
        project(record, "customs_line", spec)
