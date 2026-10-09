"""人工关联差异、只读复核及不可变留痕；隔离SQLite不代表MySQL并发验收。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.core.middleware import register_error_handlers
from backend.modules.matching import dao
from backend.modules.matching.controller import create_router
from backend.modules.matching.dto import LinkPair, LinkRequest, LinkSelection
from backend.modules.matching.entity import allocations, link_batches, metadata
from backend.modules.matching.service import MatchingService
from backend.tests.test_matching_allocations import sample
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool


@pytest.fixture
def manual_service(monkeypatch):
    invoice, heads, lines = sample()
    invoice["sourceStatus"] = "unknown"
    heads[0]["supplier_name"] = "另一供应商"
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine)

    class Storage:
        dialect = SimpleNamespace(name="mysql")

        def begin(self):
            return engine.begin()

        def connect(self):
            return engine.connect()

    invoices, purchases = Mock(), Mock()
    invoices.invoice_detail.return_value = invoice
    purchases.read.return_value = heads, lines
    monkeypatch.setattr("backend.modules.matching.service.matching_invoice", lambda *_: invoice)
    service = MatchingService(invoices, purchases, Storage())
    yield service, invoice, heads, lines, engine
    engine.dispose()


def body_for(service, **changes):
    return LinkRequest(
        **{
            "requestId": uuid4(),
            "snapshot": service.preview(1, "owner")["snapshot"],
            "pairs": [LinkPair(invoiceLineId="11", purchaseLineId="21")],
            "manualConfirmation": True,
            "manualReason": "已核实供应商更名；本票仅记录采购对应关系，差异另行处理。",
            **changes,
        }
    )


def test_review_and_manual_link_preserve_discrepancies_and_idempotency(manual_service):
    service, invoice, heads, lines, engine = manual_service
    body = body_for(service)
    review = service.review_links(1, body, "owner")
    assert review["allowed"] and review["requiresManualConfirmation"]
    assert any("供应商" in warning and "另一供应商" in warning for warning in review["warnings"])
    assert any("汇总不一致" in warning for warning in review["warnings"])
    assert any("状态未知" in warning for warning in review["warnings"])
    with pytest.raises(ApiError, match="状态未知"):
        service.link(1, body.model_copy(update={"manualConfirmation": False}), "owner")
    with pytest.raises(ApiError, match="确认说明"):
        service.link(1, body.model_copy(update={"manualReason": "  "}), "owner")
    assert service.link(1, body, "owner")["linkedLines"] == 1
    assert "已经保存" in service.link(1, body, "owner")["message"]
    with pytest.raises(ApiError, match="请求标识"):
        service.link(1, body.model_copy(update={"manualReason": "另一理由"}), "owner")
    history = service.preview(1, "owner")["links"][0]
    assert history["manualConfirmation"] and history["manualReason"] == body.manualReason
    assert history["warnings"] == review["warnings"] and not history["needsReview"]
    with engine.connect() as connection:
        saved = connection.execute(select(link_batches)).mappings().one()
        assert saved["actor"] == "owner" and saved["created_at"]
        assert saved["source_snapshot"]["selectedCandidates"][0]["supplier"] == "另一供应商"
        assert connection.scalar(select(func.count()).select_from(allocations)) == 0
    lines[0]["amount"] = Decimal("101")
    assert service.preview(1, "owner")["links"][0]["needsReview"]


def test_manual_search_reaches_orders_outside_automatic_candidates(manual_service):
    service, invoice, heads, lines, _engine = manual_service
    invoice["remark"] = "无采购线索"
    assert service.preview(1, "owner")["candidates"] == []
    search = service.preview(1, "owner", purchase_query="CH1", invoice_line_id="11")
    assert search["candidateCount"] == 1 and search["candidates"][0]["basis"] == "人工搜索选择"
    assert search["snapshot"] == service.preview(1, "owner")["snapshot"]
    assert service.preview(1, "owner", purchase_query="不存在")["candidateCount"] == 0
    with pytest.raises(ApiError, match="发票明细不存在"):
        service.preview(1, "owner", purchase_query="CH1", invoice_line_id="999")
    with pytest.raises(ApiError, match="请输入"):
        service.preview(1, "owner", purchase_query="  ")
    assert service.link(1, body_for(service), "owner")["linkedLines"] == 1


def test_search_paginates_and_can_confirm_beyond_first_hundred(manual_service):
    service, invoice, heads, lines, _engine = manual_service
    lines.extend({**lines[0], "id": index} for index in range(22, 123))
    first = service.preview(1, "owner", purchase_query="CH1", invoice_line_id="11")
    second = service.preview(1, "owner", purchase_query="CH1", invoice_line_id="11", page=2)
    assert len(first["candidates"]) == 100 and first["hasNext"]
    assert len(second["candidates"]) == 2 and not second["hasNext"]
    assert first["snapshot"] == second["snapshot"]
    body = body_for(service, pairs=[LinkPair(invoiceLineId="11", purchaseLineId="122")])
    assert service.review_links(1, body, "owner")["allowed"]
    assert service.link(1, body, "owner")["linkedLines"] == 1


def test_one_purchase_order_links_multiple_invoice_lines(manual_service):
    service, invoice, _heads, lines, _engine = manual_service
    invoice["lines"][0].update(quantity="3", gross="30")
    invoice["lines"].append({**invoice["lines"][0], "id": "12", "item": "包装盒"})
    lines[0].update(declaration_quantity=Decimal("3"), amount=Decimal("30"))
    lines.append({**lines[0], "id": 22, "declaration_name": "包装盒"})
    search = service.preview(1, "owner", purchase_query="CH1")
    assert {row["invoiceLineId"] for row in search["candidates"]} == {"11", "12"}
    assert {row["purchaseLineId"] for row in search["candidates"]} == {"21", "22"}
    body = body_for(
        service,
        pairs=[
            LinkPair(invoiceLineId="11", purchaseLineId="21"),
            LinkPair(invoiceLineId="12", purchaseLineId="22"),
        ],
    )
    assert service.review_links(1, body, "owner")["allowed"]
    assert service.link(1, body, "owner")["linkedLines"] == 2
    history = service.preview(1, "owner")["links"]
    assert {row["orderNo"] for row in history} == {"CH1"}
    assert {row["invoiceLineId"] for row in history} == {"11", "12"}


def test_list_summary_tracks_manual_confirmation_and_source_changes(manual_service):
    service, invoice, _heads, lines, _engine = manual_service
    service.invoices.invoice_details.return_value = [invoice]
    before = service.summaries(["1", "1"], "owner")["rows"][0]
    assert before["method"] == "未关联" and before["confidence"] == "有差异"
    service.invoices.invoice_details.assert_called_once_with([1], "owner")
    service.purchases.read.assert_called_once_with("owner")
    service.link(1, body_for(service), "owner")
    confirmed = service.summaries(["1"], "owner")["rows"][0]
    assert confirmed["method"] == "人工关联"
    assert confirmed["confidence"] == "有差异" and confirmed["validation"] == "已确认（有差异）"
    assert invoice["sourceStatus"] == "unknown"
    lines[0]["amount"] = Decimal("101")
    stale = service.summaries(["1"], "owner")["rows"][0]
    assert stale["validation"] == "来源变化，待复核"


def test_summary_http_auth_limits_and_unavailable_storage(manual_service):
    service, invoice, _heads, _lines, _engine = manual_service
    service.invoices.invoice_details.return_value = [invoice]
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_router(service))

    def denied():
        raise ApiError(401, "请先登录")

    app.dependency_overrides[current_owner] = denied
    with TestClient(app) as client:
        assert client.post("/api/matching/summaries", json={"invoiceIds": ["1"]}).status_code == 401
        app.dependency_overrides[current_owner] = lambda: "owner"
        assert (
            client.post("/api/matching/summaries", json={"invoiceIds": ["1"]}).json()["rows"][0]["invoiceId"]
            == "1"
        )
        for ids in ([], ["1"] * 101, ["0"], ["-1"], ["abc"], [1]):
            assert client.post("/api/matching/summaries", json={"invoiceIds": ids}).status_code == 400
        assert (
            client.post("/api/matching/summaries", json={"invoiceIds": ["99999999999999999999"]}).status_code
            == 422
        )
        service.invoices.invoice_details.side_effect = ApiError(404, "发票不可见")
        service.purchases.read.reset_mock()
        assert client.post("/api/matching/summaries", json={"invoiceIds": ["9"]}).status_code == 404
        service.purchases.read.assert_not_called()
        service.invoices.invoice_details.side_effect = None
        service.engine = None
        assert client.post("/api/matching/summaries", json={"invoiceIds": ["1"]}).status_code == 503


@pytest.mark.parametrize(
    "change",
    [
        "red",
        "incomplete",
        "buyer",
        "currency",
        "negative",
        "uncovered",
        "foreign",
        "duplicate",
        "seller_missing",
    ],
)
def test_manual_confirmation_does_not_bypass_hard_constraints(manual_service, change):
    service, invoice, heads, lines, engine = manual_service
    changes = {}
    if change == "red":
        invoice["sourceStatus"] = "red_offset"
    elif change == "incomplete":
        invoice["sourceComplete"] = False
    elif change == "buyer":
        invoice["buyer"] = "其他公司"
    elif change == "currency":
        invoice["currency"] = "USD"
    elif change == "negative":
        lines[0]["amount"] = Decimal("-10")
    elif change == "uncovered":
        invoice["lines"].append({**invoice["lines"][0], "id": "12"})
    elif change == "foreign":
        changes["pairs"] = [LinkPair(invoiceLineId="11", purchaseLineId="999")]
    elif change == "seller_missing":
        invoice["seller"] = None
    else:
        changes["pairs"] = [LinkPair(invoiceLineId="11", purchaseLineId="21")] * 2
    body = body_for(service, **changes)
    review = service.review_links(1, body, "owner")
    assert not review["allowed"] and review["reason"]
    with pytest.raises(ApiError):
        service.link(1, body, "owner")
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(link_batches)) == 0


def test_stale_snapshot_and_occupied_purchase_still_block_manual_link(manual_service):
    service, invoice, heads, lines, _engine = manual_service
    body = body_for(service)
    heads[0]["supplier_name"] = "更新后的供应商"
    with pytest.raises(ApiError, match="发生变化"):
        service.review_links(1, body, "owner")
    with pytest.raises(ApiError, match="发生变化"):
        service.link(1, body, "owner")
    service.link(1, body_for(service), "owner")
    invoice["id"] = "2"
    with pytest.raises(ApiError, match="已有整票关联"):
        service.link(2, body_for(service), "owner")


def test_failure_rolls_back_manual_audit_and_relation(manual_service, monkeypatch):
    from sqlalchemy.exc import OperationalError

    service, _invoice, _heads, _lines, engine = manual_service
    original = dao.insert_links

    def fail(connection, batch, pairs):
        original(connection, batch, pairs)
        raise OperationalError("test", {}, Exception("rollback"))

    monkeypatch.setattr(dao, "insert_links", fail)
    with pytest.raises(ApiError, match="结果不明"):
        service.link(1, body_for(service), "owner")
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(link_batches)) == 0


def test_manual_http_validation_and_authorization(manual_service):
    service, _invoice, _heads, _lines, _engine = manual_service
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_router(service))

    def denied():
        raise ApiError(401, "请先登录")

    app.dependency_overrides[current_owner] = denied
    with TestClient(app) as client:
        path = "/api/matching/invoices/1"
        assert client.get(path + "?purchaseQuery=CH1").status_code == 401
        body = body_for(service).model_dump(mode="json")
        selection = LinkSelection.model_validate(
            {key: body[key] for key in ("snapshot", "pairs")}
        ).model_dump()
        assert client.post(path + "/links/review", json=selection).status_code == 401
        app.dependency_overrides[current_owner] = lambda: "owner"
        assert client.get(path + "?purchaseQuery=CH1&invoiceLineId=11").json()["candidateCount"] == 1
        assert client.post(path + "/links/review", json=selection).json()["requiresManualConfirmation"]
        for changes in ({"manualConfirmation": "yes"}, {"manualReason": "a" * 1001}, {"actor": "other"}):
            assert client.post(path + "/links", json={**body, **changes}).status_code == 400
        assert client.post(path + "/links", json={**body, "manualReason": "  "}).status_code == 422
        assert client.post(path + "/links", json=body).status_code == 200
