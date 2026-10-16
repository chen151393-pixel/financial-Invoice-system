"""超过原 300 条门槛时仍完整保存、去重，并在后续失败时保持整批原子性。"""

from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import pytest
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import NetSuite
from backend.integrations.netsuite.read_batch import RecordReader
from backend.modules.source.service.storage_service import StorageService
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_source_storage import rows
from backend.tests.test_sync_optimization import batch as batch


def expand_lines(batch, section):
    ns, page, records, calls = batch
    kind = ns.settings.pl_lookup[section]["type"]
    template = next(value for (record_type, _), value in records.items() if record_type == kind)
    for index in range(301):
        row = deepcopy(template)
        if section == "purchase_line":
            row["custrecord_swc_subpo_item_lineid"] = str(index + 10)
        records[kind, str(100000 + index)] = row
    return ns, page, records, calls, kind


@pytest.mark.parametrize(
    "section,table",
    [
        ("customs_line", "source_customs_lines"),
        ("purchase_line", "source_purchase_order_lines"),
    ],
)
def test_more_than_three_hundred_lines_saved_without_duplicates(batch, engine, section, table):
    ns, page, _, calls, _ = expand_lines(batch, section)
    service = StorageService(ns, engine)
    first = service.sync_page("customs-declarations", lambda: {"rows": page})
    assert len(rows(engine, f"SELECT id FROM {table} WHERE is_active = 1")) == 341
    assert max(Counter(calls).values()) == 1
    counts = first["storage"]["customs" if section == "customs_line" else "purchase"]
    assert counts["linesCreated"] == 341
    calls.clear()
    repeated = service.sync_page("customs-declarations", lambda: {"rows": page})
    assert repeated["storage"]["customs"]["created"] == 0
    assert repeated["storage"]["purchase"]["created"] == 0
    assert len(rows(engine, f"SELECT id FROM {table}")) == 341
    assert max(Counter(calls).values()) == 1
    assert {r["currency"] for r in rows(engine, "SELECT currency FROM source_purchase_orders")} == {"CNY"}


def test_failure_beyond_old_limit_never_saves_partial_documents(batch, engine):
    ns, page, _, calls, kind = expand_lines(batch, "purchase_line")
    ns.settings.sync_read_workers = 1
    original = ns.request

    def request(method, record_type, identity, **kwargs):
        if record_type == kind and identity == "100300":
            raise ApiError(502, "最后一条明细读取失败")
        return original(method, record_type, identity, **kwargs)

    ns.request = request
    with pytest.raises(ApiError, match="最后一条明细"):
        StorageService(ns, engine).sync_page("customs-declarations", lambda: {"rows": page})
    assert sum(call[0] == "detail" for call in calls) > 300
    assert rows(engine, "SELECT id FROM source_customs_declarations") == []
    assert rows(engine, "SELECT id FROM source_purchase_orders") == []


def test_first_failure_does_not_start_entire_large_queue():
    calls = []

    def request(method, kind, identity, **kwargs):
        calls.append(identity)
        raise ApiError(502, "NS 读取失败")

    ns = SimpleNamespace(settings=Settings(sync_read_workers=1), request=request, validate=lambda *a: None)
    with pytest.raises(ApiError, match="NS 读取失败"):
        RecordReader(ns).prefetch("customrecord_line", [str(i) for i in range(1, 1002)], "读取明细")
    assert calls == ["1"]


def test_duplicate_on_page_after_old_limit_is_still_rejected():
    ns = NetSuite(Settings(record_types=["customrecord_line"]))

    def request(*args, query_params, **kwargs):
        offset = query_params["offset"]
        return {
            "data": {
                "items": [{"id": str(i)} for i in range(offset + 1, offset + 101)]
                if offset < 300
                else [{"id": "1"}],
                "hasMore": offset < 300,
            }
        }

    ns.request = request
    try:
        with pytest.raises(ApiError, match="分页数据重复"):
            ns.filtered_ids("customrecord_line", "parent", "7", reference=True)
    finally:
        ns.close()
