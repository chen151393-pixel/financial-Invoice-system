"""逐关联组保存：部分失败不丢失其他成功单据，组内原子，结果未知停止。"""

from collections import Counter

from backend.core.errors import ApiError
from backend.modules.source.service.storage_service import StorageService
from backend.modules.sync.dto.source_dto import PullRequest
from backend.modules.sync.pull_service import PullService
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_source_storage import rows
from backend.tests.test_sync_optimization import batch as batch
from sqlalchemy.exc import OperationalError


def page_result(page):
    return {
        "rows": [{**row, "number": row["record"]["name"]} for row in page],
        "count": len(page),
        "hasMore": False,
        "nextOffset": None,
    }


def invalid_price(ns, records):
    kind = ns.settings.pl_lookup["purchase_line"]["type"]
    records[kind, "2011"]["custrecord_swc_subpo_item_ratewithrate"] = "not-a-price"


def test_invalid_unit_price_does_not_discard_other_committed_groups(batch, engine):
    ns, page, records, _ = batch
    invalid_price(ns, records)
    result = StorageService(ns, engine).sync_partial_page("customs-declarations", lambda: page_result(page))
    assert result["batch"]["counts"] == {"saved": 19, "failed": 1, "unknown": 0, "not_processed": 0}
    assert result["batch"]["status"] == "partial" and result["batch"]["canContinue"]
    failure = next(item for item in result["batch"]["items"] if item["status"] == "failed")
    assert failure["id"] == "871" and "unit_price" in failure["reason"]
    assert len(rows(engine, "SELECT id FROM source_customs_declarations")) == 19
    assert len(rows(engine, "SELECT id FROM source_purchase_orders")) == 19
    assert result["storage"]["purchase"]["created"] == 19
    # 修复后重拉只新增失败组，其余按稳定身份更新。
    records[ns.settings.pl_lookup["purchase_line"]["type"], "2011"][
        "custrecord_swc_subpo_item_ratewithrate"
    ] = "10.05"
    again = StorageService(ns, engine).sync_partial_page("customs-declarations", lambda: page_result(page))
    assert again["storage"]["purchase"]["created"] == 1
    assert again["batch"]["counts"]["saved"] == 20
    assert len(rows(engine, "SELECT id FROM source_purchase_orders")) == 20


def test_failed_refresh_keeps_previous_complete_group(batch, engine):
    ns, page, records, _ = batch
    service = StorageService(ns, engine)
    service.sync_page("customs-declarations", lambda: page_result(page[:2]))
    before = rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY id")
    invalid_price(ns, records)
    result = service.sync_partial_page("customs-declarations", lambda: page_result(page[1:2]))
    assert result["batch"]["counts"]["failed"] == 1
    assert result["storage"]["savedAt"] is None
    assert rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY id") == before


def test_children_of_same_customs_are_one_failure_unit(batch, engine):
    ns, _, records, calls = batch
    kind = ns.settings.pl_lookup["purchase"]["type"]
    records[kind, "201"][ns.settings.pl_lookup["purchase"]["customs"]] = {"id": "870"}
    page = [{"id": key, "record": records[kind, key]} for key in ("200", "201", "202")]
    invalid_price(ns, records)
    result = StorageService(ns, engine).sync_partial_page("sub-purchase-orders", lambda: page_result(page))
    assert result["batch"]["counts"]["failed"] == 2
    assert result["batch"]["counts"]["saved"] == 1
    assert [
        r["ns_internal_id"] for r in rows(engine, "SELECT ns_internal_id FROM source_purchase_orders")
    ] == ["202"]
    # 同一报关组仅反查一次，不因页内两张子采购重复保存。
    query = ("list", kind, "870")
    assert Counter(calls)[query] == 1


def test_detail_read_failure_isolated_to_complete_group(batch, engine):
    ns, page, _, _ = batch
    original = ns.projected_records

    def request(kind, ids, fields):
        if "2011" in ids:
            raise ApiError(502, "明细读取失败")
        return original(kind, ids, fields)

    ns.projected_records = request
    result = StorageService(ns, engine).sync_partial_page(
        "customs-declarations", lambda: page_result(page[:3])
    )
    assert result["batch"]["counts"]["saved"] == 2
    assert result["batch"]["counts"]["failed"] == 1
    assert len(rows(engine, "SELECT id FROM source_customs_declarations")) == 2


def test_unknown_commit_keeps_prior_counts_and_stops_remaining(batch, engine, monkeypatch):
    ns, page, _, _ = batch
    service = StorageService(ns, engine)
    original = service.commit
    calls = []

    def save(*args):
        calls.append(True)
        saved = original(*args)
        if len(calls) == 2:
            # 模拟已提交但确认响应丢失，不能用捕获异常推断该组未写入。
            raise OperationalError("", {}, Exception("connection lost"))
        return saved

    monkeypatch.setattr(service, "commit", save)
    result = service.sync_partial_page("customs-declarations", lambda: page_result(page[:3]))
    assert result["batch"]["counts"] == {"saved": 1, "failed": 0, "unknown": 1, "not_processed": 1}
    assert result["batch"]["status"] == "interrupted" and not result["batch"]["canContinue"]
    assert result["storage"]["customs"]["created"] == 1
    assert len(calls) == 2 and len(rows(engine, "SELECT id FROM source_customs_declarations")) == 2


def test_transaction_business_failure_rolls_back_only_its_group(batch, engine, monkeypatch):
    ns, page, _, _ = batch
    service = StorageService(ns, engine)
    original = service._write

    def write(connection, account, bundle, documents, now):
        value = original(connection, account, bundle, documents, now)
        if documents["customs"][0]["ns_internal_id"] == "871":
            raise ApiError(422, "关联校验失败")
        return value

    monkeypatch.setattr(service, "_write", write)
    result = service.sync_partial_page("customs-declarations", lambda: page_result(page[:3]))
    assert result["batch"]["counts"]["saved"] == 2
    assert len(rows(engine, "SELECT id FROM source_customs_declarations")) == 2
    assert len(rows(engine, "SELECT id FROM source_purchase_orders")) == 2


def test_header_failure_returns_page_scope_and_saves_other_headers(batch, engine):
    ns, page, _, _ = batch
    ns.settings.missing = lambda: []
    original = ns.request

    def request(method, kind, identity=None, **kwargs):
        if identity is None:
            return {"data": {"items": [{"id": row["id"]} for row in page[:3]], "hasMore": False}}
        if identity == "871":
            raise ApiError(502, "单头读取失败")
        return original(method, kind, identity, **kwargs)

    ns.request = request
    result = PullService(ns.settings, ns, StorageService(ns, engine)).pull_and_save(
        "customs-declarations", PullRequest(partialSave=True)
    )
    assert result["count"] == 3 and len(result["rows"]) == 2
    assert result["batch"]["counts"]["saved"] == 2
    assert result["batch"]["counts"]["failed"] == 1
    assert result["nextOffset"] is None


def test_empty_page_is_complete_without_saved_timestamp(batch, engine):
    ns, _, _, _ = batch
    result = StorageService(ns, engine).sync_partial_page("customs-declarations", lambda: page_result([]))
    assert result["batch"]["status"] == "completed"
    assert result["storage"]["savedAt"] is None
    assert not result["batch"]["items"]


def test_saved_group_can_be_reviewed_and_generate_tasks(batch, engine):
    from decimal import Decimal

    from backend.app import create_events
    from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
    from backend.modules.review.service.review_service import ReviewService
    from backend.modules.source.public import DeclarationService

    ns, page, records, _ = batch
    invalid_price(ns, records)
    events = create_events()
    result = StorageService(ns, engine, events).sync_partial_page(
        "customs-declarations", lambda: page_result(page[:2])
    )
    assert result["batch"]["counts"]["saved"] == 1
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    review.approve(int(group.id), ApproveRequest(contentSha256=group.contentSha256), "user:admin")
    amounts = rows(engine, "SELECT expected_amount FROM task_lines ORDER BY id")
    assert [Decimal(str(row["expected_amount"])) for row in amounts] == [Decimal("100.50"), Decimal("20")]


def test_lock_conflict_stops_later_groups_without_losing_prior_success(batch, engine, monkeypatch):
    ns, page, _, _ = batch
    service = StorageService(ns, engine)
    original = service.commit
    calls = []

    def save(*args):
        calls.append(True)
        if len(calls) == 2:
            raise ApiError(409, "同步连接已失去占用，未保存")
        return original(*args)

    monkeypatch.setattr(service, "commit", save)
    result = service.sync_partial_page("customs-declarations", lambda: page_result(page[:3]))
    assert result["batch"]["counts"] == {"saved": 1, "failed": 1, "unknown": 0, "not_processed": 1}
    assert not result["batch"]["canContinue"] and len(calls) == 2
    assert len(rows(engine, "SELECT id FROM source_customs_declarations")) == 1
