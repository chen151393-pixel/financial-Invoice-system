"""合成 NS 验证请求缩减、并发上限、完整性与主链路；不连接真实 NS。"""

from collections import Counter
from copy import deepcopy
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest
from backend.core.config import Settings, load_settings
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import NetSuite
from backend.integrations.netsuite.read_batch import RecordReader
from backend.modules.source.service.ns_reader import PlReader
from backend.modules.source.service.storage_service import StorageService
from backend.tests.test_source_storage import PARENT, customs, purchase, rows
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns


@pytest.fixture
def batch(ns):
    mapping, records, page, calls = ns.settings.pl_lookup, {}, [], []
    for index in range(20):
        identity, head, details = customs(str(870 + index))
        page.append({"id": identity, "record": head})
        records[mapping["customs"]["type"], identity] = head
        records.update({(mapping["customs_line"]["type"], key): value for key, value in details})
        identity, head, details = purchase(str(200 + index), identity)
        records[mapping["purchase"]["type"], identity] = head
        records.update({(mapping["purchase_line"]["type"], key): value for key, value in details})
    records[mapping["pl"]["type"], "783"] = {mapping["pl"]["number"]: "PL001"}
    ns.settings.sync_read_workers = 2
    ns.settings.finance_source_script = ""
    ns.settings.pl_restlet_script = ""
    ns.validate = lambda *args: None

    def request(method, kind, identity, **kwargs):
        assert method == "GET" and kwargs["exact_numbers"]
        calls.append(("detail", kind, identity))
        return {"data": deepcopy(records[kind, identity])}

    def filtered(kind, field, identities, **kwargs):
        calls.append(("list", kind, str(identities)))
        ids = identities if isinstance(identities, list) else [identities]
        return [
            key
            for (record_type, key), record in records.items()
            if record_type == kind and record.get(field, {}).get("id") in ids
        ]

    ns.request, ns.filtered_ids = request, filtered
    ns.relation_rows = lambda kind, ids: [PARENT] if kind == "parent_headers" else []
    return ns, page, records, calls


def test_twenty_customs_batch_reduces_lists_and_keeps_all_data(batch, engine):
    ns, page, _, calls = batch
    progress = []
    result = StorageService(ns, engine).sync_page(
        "customs-declarations",
        lambda: {"rows": page},
        progress=lambda *value: progress.append(value),
    )
    counts = Counter(kind for kind, *_ in calls)
    # 原来每张报关分别查询三类列表：20 * 3；现在同类父引用合并为 3 次。
    assert counts == {"list": 3, "detail": 101}
    assert max(Counter(calls).values()) == 1
    assert result["storage"]["customs"]["created"] == 20
    assert result["storage"]["purchase"]["created"] == 20
    assert result["storage"]["customs"]["linesCreated"] == 40
    assert result["storage"]["purchase"]["linesCreated"] == 40
    assert {row["currency"] for row in rows(engine, "SELECT currency FROM source_purchase_orders")} == {"CNY"}
    assert any(value[0] == "读取报关明细" and value[1:] == (40, 40) for value in progress)
    assert progress[-1][0] == "保存到本地数据库，等待整批提交"
    calls.clear()
    repeated = StorageService(ns, engine).sync_page("customs-declarations", lambda: {"rows": page})
    assert repeated["storage"]["customs"]["created"] == 0
    assert len(rows(engine, "SELECT id FROM source_purchase_orders")) == 20
    assert Counter(kind for kind, *_ in calls)["detail"] == 101  # 下一批重新读取最新 NS 值。


def test_child_entry_keeps_membership_check_and_reuses_page_headers(batch):
    ns, _, records, calls = batch
    kind = ns.settings.pl_lookup["purchase"]["type"]
    page = [
        {"id": key, "record": value} for (record_type, key), value in records.items() if record_type == kind
    ]
    result = PlReader(ns).collect_records("sub-purchase-orders", page)
    assert len(result["purchases"]) == len(result["customs"]) == 20
    assert not any(call[0] == "detail" and call[1] == kind for call in calls)
    assert max(Counter(calls).values()) == 1
    original = ns.filtered_ids
    ns.filtered_ids = lambda kind, field, value, **kw: (
        [] if field == ns.settings.pl_lookup["purchase"]["customs"] else original(kind, field, value, **kw)
    )
    with pytest.raises(ApiError, match="读取期间子采购报关引用发生变化"):
        PlReader(ns).collect_records("sub-purchase-orders", page)


@pytest.mark.parametrize("mode", ["duplicate", "wrong_parent", "read_failure"])
def test_invalid_batch_never_saves_partial_data(batch, engine, mode):
    ns, page, records, _ = batch
    original = ns.filtered_ids
    if mode == "duplicate":
        ns.filtered_ids = lambda *args, **kw: original(*args, **kw) * 2
    else:
        spec = ns.settings.pl_lookup["customs_line"]
        if mode == "wrong_parent":
            records[spec["type"], "8701"][spec["parent"]] = {"id": "9999"}
            ns.filtered_ids = lambda *args, **kw: (
                original(*args, **kw) + (["8701"] if args[0] == spec["type"] else [])
            )
        else:
            original_request = ns.request

            def fail(method, kind, identity, **kw):
                if identity == "8701":
                    raise ApiError(502, "模拟 NS 超时")
                return original_request(method, kind, identity, **kw)

            ns.request = fail
    with pytest.raises(ApiError):
        StorageService(ns, engine).sync_page("customs-declarations", lambda: {"rows": page})
    assert rows(engine, "SELECT id FROM source_customs_declarations") == []
    assert rows(engine, "SELECT id FROM source_purchase_orders") == []


def test_detail_parallelism_is_bounded_and_duplicate_ids_are_reused():
    lock, barrier, calls = Lock(), Barrier(2), []
    active = maximum = 0

    def request(method, kind, identity, **kw):
        nonlocal active, maximum
        with lock:
            calls.append(identity)
            active += 1
            maximum = max(maximum, active)
        barrier.wait(timeout=5)
        with lock:
            active -= 1
        return {"data": {"id": identity}}

    ns = SimpleNamespace(settings=Settings(sync_read_workers=2), request=request, validate=lambda *args: None)
    reader = RecordReader(ns)
    reader.prefetch("customrecord_line", ["1", "2", "1", "3", "4"], "读取明细")
    reader.prefetch("customrecord_line", ["1", "2"], "读取明细")
    assert len(calls) == 4 and maximum == 2


def test_bulk_filter_is_exact_and_keeps_pagination_checks():
    ns = NetSuite(Settings(record_types=["customrecord_line"]))
    calls = []

    def request(*args, **kwargs):
        calls.append(kwargs["query_params"])
        return {"data": {"items": [{"id": "1"}], "hasMore": False}}

    ns.request = request
    assert ns.filtered_ids("customrecord_line", "parent", ["7", "8", "7"], reference=True) == ["1"]
    assert calls[0]["q"] == "parent ANY_OF [7,8]"
    for value in [[], ["7] OR id IS 1"], [str(i) for i in range(21)]]:
        with pytest.raises(ApiError):
            ns.filtered_ids("customrecord_line", "parent", value, reference=True)
    assert len(calls) == 1
    ns.client.close()


@pytest.mark.parametrize("value", ["0", "5", "abc", "2.5"])
def test_read_concurrency_setting_rejects_unbounded_values(value):
    with pytest.raises(ValueError, match="NETSUITE_SYNC_READ_WORKERS"):
        load_settings({"NETSUITE_SYNC_READ_WORKERS": value})


@pytest.mark.parametrize(
    "response",
    [
        {"items": []},
        {"items": [], "hasMore": True},
        {"items": [{"id": "1"}, {"id": "1"}], "hasMore": False},
    ],
)
def test_bulk_list_rejects_incomplete_or_duplicate_pages(response):
    ns = NetSuite(Settings(record_types=["customrecord_line"]))
    ns.request = lambda *args, **kw: {"data": response}
    with pytest.raises(ApiError):
        ns.filtered_ids("customrecord_line", "parent", ["7", "8"], reference=True)
    ns.client.close()


def test_bulk_list_reads_all_pages_before_returning():
    ns = NetSuite(Settings(record_types=["customrecord_line"]))
    offsets = []

    def request(*args, query_params, **kwargs):
        offset = query_params["offset"]
        offsets.append(offset)
        return {
            "data": {
                "items": [{"id": str(i)} for i in range(offset + 1, min(offset + 100, 401) + 1)],
                "hasMore": offset + 100 < 401,
            }
        }

    ns.request = request
    assert len(ns.filtered_ids("customrecord_line", "parent", ["7", "8"], reference=True)) == 401
    assert offsets == [0, 100, 200, 300, 400]
    ns.client.close()


def test_large_detail_collection_keeps_progress_and_cache():
    calls, progress = [], []

    def request(method, kind, identity, **kw):
        calls.append(identity)
        return {"data": {"id": identity}}

    ns = SimpleNamespace(settings=Settings(), validate=lambda *args: None, request=request)
    reader = RecordReader(ns, lambda *value: progress.append(value))
    ids = [str(i) for i in range(1, 602)]
    reader.prefetch("customrecord_line", ids + ids[:10], "读取明细")
    reader.prefetch("customrecord_line", ids, "读取明细")
    assert len(calls) == len(set(calls)) == len(reader.cache) == 601
    assert progress[-1] == ("读取明细", 601, 601)
