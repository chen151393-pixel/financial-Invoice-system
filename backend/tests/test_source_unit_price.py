"""单价展示精度兼容：原始单价留存，数量、金额及审核开票依据保持原值。"""

import json
from decimal import Decimal

import pytest
from backend.app import create_events
from backend.core.errors import ApiError
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.mapper.storage_mapper import project
from backend.modules.source.policy.ns_config import parse_config
from backend.modules.source.public import DeclarationService
from backend.modules.source.service.storage_service import StorageService
from backend.tests.test_source_optional_sync import source as source
from backend.tests.test_source_storage import declaration, rows
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns

LINE_CASES = [("purchase_line", "2001", "tax_inclusive_price"), ("customs_line", "8701", "unit_price")]


@pytest.mark.parametrize("kind,identity,key", LINE_CASES)
@pytest.mark.parametrize(
    "value,expected",
    [
        ("10.123456784", "10.12345678"),
        ("10.123456785", "10.12345679"),
        (Decimal("-10.123456785"), "-10.12345679"),
        (Decimal("10.12345678901234567890123456789"), "10.12345679"),
        ("10.050000000000", "10.05"),
        ("9999999999999999.999999994", "9999999999999999.99999999"),
        ("1E-1000", "0"),
        (0, "0"),
        (None, None),
        ("", None),
    ],
)
def test_price_precision_is_normalized_only_in_projection(source, kind, identity, key, value, expected):
    ns, _, _, records = source
    spec = getattr(parse_config(ns.settings), kind)
    record = records[spec.type, identity]
    record[spec.storage_fields[key]] = value
    columns, _ = project(record, kind, spec)
    assert columns["unit_price"] == (Decimal(expected) if expected is not None else None)
    assert record[spec.storage_fields[key]] == value


@pytest.mark.parametrize("kind,identity,key", LINE_CASES)
@pytest.mark.parametrize(
    "value",
    [
        "not-a-price",
        True,
        1.25,
        {},
        [],
        "NaN",
        "Infinity",
        "1e9999",
        "10000000000000000",
        "9999999999999999.999999995",
        "-9999999999999999.999999995",
    ],
)
def test_invalid_price_or_rounding_overflow_still_rejected(source, kind, identity, key, value):
    ns, _, _, records = source
    spec = getattr(parse_config(ns.settings), kind)
    record = records[spec.type, identity]
    record[spec.storage_fields[key]] = value
    with pytest.raises(ApiError, match="unit_price"):
        project(record, kind, spec)


@pytest.mark.parametrize("kind,identity,key", LINE_CASES)
@pytest.mark.parametrize("field,value", [("amount", "1.1234567"), ("quantity", "1.123456789")])
def test_amount_and_quantity_precision_rules_are_not_relaxed(source, kind, identity, key, field, value):
    ns, _, _, records = source
    spec = getattr(parse_config(ns.settings), kind)
    record = records[spec.type, identity]
    record[spec.storage_fields[key]] = "1.123456789"
    record[spec.storage_fields[field]] = value
    with pytest.raises(ApiError, match=field):
        project(record, kind, spec)


def set_precise_prices(source):
    ns, _, _, records = source
    for kind, identity, key in LINE_CASES:
        spec = getattr(parse_config(ns.settings), kind)
        records[spec.type, identity][spec.storage_fields[key]] = Decimal("1.1234567890123456789")


def assert_saved_values(engine, ns):
    for table, expected_amount in (("source_purchase_order_lines", "100.50"), ("source_customs_lines", "15")):
        line = rows(engine, f"SELECT unit_price, quantity, amount FROM {table} ORDER BY id")[0]
        assert Decimal(str(line["unit_price"])) == Decimal("1.12345679")
        assert Decimal(str(line["quantity"])) == Decimal("10")
        assert Decimal(str(line["amount"])) == Decimal(expected_amount)
    head = rows(engine, "SELECT total_amount, currency FROM source_purchase_orders")[0]
    assert Decimal(str(head["total_amount"])) == Decimal("120.50") and head["currency"] == "CNY"
    originals = [json.loads(row["payload"]) for row in rows(engine, "SELECT payload FROM source_raw_records")]
    for kind, identity, key in LINE_CASES:
        spec = getattr(parse_config(ns.settings), kind)
        original = next(raw for raw in originals if raw.get("lineType") == spec.type)
        record = next(line["record"] for line in original["lines"] if line["id"] == identity)
        assert record[spec.storage_fields[key]] == "1.1234567890123456789"


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("kind", ["customs-declarations", "sub-purchase-orders"])
def test_precise_prices_preserve_raw_amounts_and_review_task_chain(source, engine, partial, kind):
    ns, page, _, records = source
    set_precise_prices(source)
    if kind == "sub-purchase-orders":
        head = records[ns.settings.pl_lookup["purchase"]["type"], "200"]
        page = {**page, "rows": [{"id": "200", "number": head["name"], "record": head}]}
    events = create_events()
    storage = StorageService(ns, engine, events)
    save = storage.sync_partial_page if partial else storage.sync_page
    result = save(kind, lambda: page)
    if partial:
        assert result["batch"]["status"] == "completed"
        assert result["batch"]["counts"]["failed"] == 0
    assert sum("按 8 位小数" in message for message in result["storage"]["warnings"]) == 2
    assert_saved_values(engine, ns)
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    review.approve(int(group.id), ApproveRequest(contentSha256=group.contentSha256), "user:admin")
    tasks = rows(engine, "SELECT expected_amount, expected_quantity FROM task_lines ORDER BY id")
    assert [Decimal(str(row["expected_amount"])) for row in tasks] == [Decimal("100.50"), Decimal("20")]
    assert all(Decimal(str(row["expected_quantity"])) == Decimal("10") for row in tasks)
    before = declaration(engine)["content_sha256"]
    # 关联依据包含每次读取时间；这里只检查单据原始快照的幂等性。
    raw_query = "SELECT id FROM source_raw_records WHERE record_type != 'relation_evidence'"
    raw_count = len(rows(engine, raw_query))
    save(kind, lambda: page)
    assert declaration(engine)["content_sha256"] == before
    assert len(rows(engine, raw_query)) == raw_count
    assert review.browse(DeclarationListQuery()).groups[0].review.status == "approved"
    assert len(rows(engine, "SELECT id FROM task_tasks")) == 1
    # 真实金额变更仍触发原有重新审核；已生成任务不会被新来源静默改写。
    spec = parse_config(ns.settings).purchase_line
    records[spec.type, "2001"][spec.storage_fields["amount"]] = Decimal("101.50")
    save(kind, lambda: page)
    assert declaration(engine)["content_sha256"] != before
    assert review.browse(DeclarationListQuery()).groups[0].review.status != "approved"
    assert rows(engine, "SELECT expected_amount, expected_quantity FROM task_lines ORDER BY id") == tasks


def test_exact_prices_have_no_precision_warning(source, engine):
    ns, page, _, records = source
    for kind, identity, key in LINE_CASES:
        spec = getattr(parse_config(ns.settings), kind)
        records[spec.type, identity][spec.storage_fields[key]] = "10.050000000000"
    result = StorageService(ns, engine).sync_page("customs-declarations", lambda: page)
    assert not any("按 8 位小数" in message for message in result["storage"]["warnings"])
