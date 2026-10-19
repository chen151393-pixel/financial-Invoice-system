"""批量字段与原详情结果等价；逐行定位、审核摘要和批内 PL 复用。"""

from collections import Counter

from backend.modules.source.service import ns_reader
from backend.modules.source.service.storage_service import StorageService
from backend.tests.test_source_optional_sync import source as source
from backend.tests.test_source_storage import declaration, rows
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_sync_optimization import batch as batch
from backend.tests.test_sync_partial_save import page_result

LINKS = "SELECT purchase_line_id,customs_line_id,evidence FROM source_customs_purchase_links WHERE status='active' ORDER BY id"
AMOUNTS = "SELECT amount,quantity,unit FROM source_purchase_order_lines ORDER BY id"


def test_projection_keeps_line_links_amounts_and_review_digest(source, engine, monkeypatch):
    ns, page, _, _ = source
    storage = StorageService(ns, engine)
    with monkeypatch.context() as legacy:
        legacy.setattr(ns_reader, "line_projection", lambda spec: None)
        storage.sync_page("customs-declarations", lambda: page)
    digest = declaration(engine)["content_sha256"]
    links = rows(engine, LINKS)
    assert sum(link["evidence"] == "local_packing" for link in links) == 2
    amounts = rows(engine, AMOUNTS)
    original = ns.projected_records

    def projected(kind, ids, fields):
        return {
            key: {field: value for field, value in record.items() if field in fields or field == "id"}
            for key, record in original(kind, ids, fields).items()
        }

    ns.projected_records = projected
    storage.sync_page("customs-declarations", lambda: page)
    assert declaration(engine)["content_sha256"] == digest
    assert rows(engine, LINKS) == links
    assert rows(engine, AMOUNTS) == amounts


def test_partial_save_reads_whole_page_once_and_rereads_pl_next_page(batch, engine):
    ns, page, records, calls = batch
    service = StorageService(ns, engine)
    result = service.sync_partial_page("customs-declarations", lambda: page_result(page))
    assert result["batch"]["counts"]["saved"] == 20
    assert result["batch"]["status"] == "completed"
    # 20 组逐组读取时为 60 次列表 + 40 次明细批次；整页一次读取后按组提交，只需 3 次列表 + 2 次明细批次。
    assert Counter(kind for kind, *_ in calls) == {"list": 3, "batch": 2, "detail": 21}
    pl = ns.settings.pl_lookup["pl"]
    records[pl["type"], "783"][pl["number"]] = "PL002"
    calls.clear()
    service.sync_partial_page("customs-declarations", lambda: page_result(page[:1]))
    assert Counter(calls)[("detail", pl["type"], "783")] == 1
    assert rows(engine, "SELECT pl_no FROM source_customs_lines WHERE id=1")[0]["pl_no"] == "PL002"
