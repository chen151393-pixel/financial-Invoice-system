"""review 模块：列表状态与筛选、整单审核、冻结行（开票口径）、事件、幂等、来源变化、权限与回滚。

来源数据经 source 模块真实保存（SQLite 隔离库，合成 NS 数据）。
"""

from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.core.events import EventBus
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.public import ReviewApproved
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService
from backend.tests.test_source_storage import ACCOUNT, bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from fastapi.testclient import TestClient

USER = "user:admin"


@pytest.fixture
def events():
    return EventBus()


@pytest.fixture
def received(events):
    captured = []
    events.subscribe(ReviewApproved, lambda connection, event: captured.append(event))
    return captured


@pytest.fixture
def service(engine, events):
    return ReviewService(engine, DeclarationService(engine), events)


@pytest.fixture
def seeded(ns, engine):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    save(ns, engine, bundle([], [customs("880")]))  # 没有关联子采购单
    return engine


def query(**values):
    return DeclarationListQuery(**values)


def group(service, record_no):
    result = service.browse(query())
    return next(item for item in result.groups if item.recordNumber == record_no)


def approve(service, item, note="核对无误", actor=USER):
    return service.approve(int(item.id), ApproveRequest(contentSha256=item.contentSha256, note=note), actor)


def test_list_states_counts_and_purchase_basis(service, seeded):
    result = service.browse(query())
    assert result.counts["all"] == 2 and result.counts["pending"] == 1 and result.counts["blocked"] == 1
    assert result.accounts == [ACCOUNT]
    pending = group(service, "CD870")
    assert pending.review.allowed and pending.review.status == "pending"
    assert pending.customsCount == 2 and pending.purchaseCount == 2 and pending.unlinkedLines == []
    line = pending.customsLines[0].purchaseLines[0]
    assert (line.quantity, line.unit, line.amount) == ("10", "个", "100.5")  # 开票口径：采购数量与单位
    assert "报关数量 5 千克" in line.note
    blocked = group(service, "CD880")
    assert blocked.review.status == "blocked" and not blocked.review.allowed and blocked.review.reason


def test_status_filter_and_pagination(service, seeded):
    assert [item.recordNumber for item in service.browse(query(status="blocked")).groups] == ["CD880"]
    first = service.browse(query(pageSize=1, page=1))
    second = service.browse(query(pageSize=1, page=2))
    assert first.total == 2 and first.pages == 2 and len(first.groups) == len(second.groups) == 1
    assert first.groups[0].id != second.groups[0].id
    assert service.browse(query(keyword="CD880")).total == 1


def test_approve_freezes_lines_and_publishes_event(service, seeded, received, engine):
    item = group(service, "CD870")
    result = approve(service, item)
    assert (
        result.review.status == "approved"
        and result.review.revision == 1
        and result.review.note == "核对无误"
    )
    assert not result.review.allowed
    record = rows(engine, "SELECT * FROM review_records")
    assert [(r["status"], r["revision"], r["approved_by"]) for r in record] == [("active", 1, USER)]
    lines = rows(engine, "SELECT * FROM review_lines ORDER BY purchase_line_id")
    assert [(r["unit"], Decimal(str(r["quantity"])), Decimal(str(r["amount"]))) for r in lines] == [
        ("个", Decimal("10"), Decimal("100.5")),
        ("个", Decimal("10"), Decimal("20")),
    ]
    assert all(r["customs_line_id"] for r in lines)  # 行级关联已带入
    assert len(received) == 1
    event = received[0]
    assert event.review_id == record[0]["id"] and event.superseded_review_id is None and event.revision == 1
    assert [line.review_line_id for line in event.lines] == [r["id"] for r in lines]
    assert service.browse(query()).counts["approved"] == 1


def test_resubmit_same_content_is_idempotent(service, seeded, received, engine):
    item = group(service, "CD870")
    approve(service, item)
    again = approve(service, item, note="重复提交")
    assert again.review.revision == 1 and again.review.note == "核对无误"
    assert len(rows(engine, "SELECT id FROM review_records")) == 1
    assert len(received) == 1


def test_stale_page_content_is_rejected(service, seeded, ns, engine):
    item = group(service, "CD870")
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    with pytest.raises(ApiError, match="来源已变化") as error:
        approve(service, item)
    assert error.value.status == 409
    assert rows(engine, "SELECT id FROM review_records") == []


def test_source_change_after_approval_requires_new_review(service, seeded, ns, engine, received):
    approve(service, group(service, "CD870"))
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    changed = group(service, "CD870")
    assert changed.review.status == "pending" and changed.review.allowed and changed.warnings
    result = approve(service, changed, note="重新审核")
    assert result.review.revision == 2 and result.review.status == "approved"
    statuses = [
        (r["revision"], r["status"]) for r in rows(engine, "SELECT * FROM review_records ORDER BY revision")
    ]
    assert statuses == [(1, "superseded"), (2, "active")]
    assert received[1].superseded_review_id == received[0].review_id


def test_blocked_declaration_cannot_be_approved(service, seeded):
    with pytest.raises(ApiError, match="没有关联的子采购单"):
        approve(service, group(service, "CD880"))


def test_service_identity_cannot_approve(service, seeded):
    with pytest.raises(ApiError) as error:
        approve(service, group(service, "CD870"), actor="service:feishu")
    assert error.value.status == 403


def test_failing_subscriber_rolls_back_review(engine, seeded):
    events = EventBus()

    def fail(connection, event):
        raise ApiError(409, "订阅方失败")

    events.subscribe(ReviewApproved, fail)
    service = ReviewService(engine, DeclarationService(engine), events)
    with pytest.raises(ApiError, match="订阅方失败"):
        approve(service, group(service, "CD870"))
    assert rows(engine, "SELECT id FROM review_records") == []
    assert rows(engine, "SELECT id FROM review_lines") == []


def test_http_query_and_approve(context, seeded, engine):
    app = create_app(context.settings, context.ns, context.engine, business_engine=engine)
    with TestClient(app) as client:
        assert client.post("/api/review/declarations/query", json={}).status_code == 401
        login = client.post(
            "/api/session",
            headers={"Origin": context.settings.origin},
            json={"username": "admin", "password": context.settings.admin_password},
        )
        assert login.status_code == 200
        headers = {"Origin": context.settings.origin}
        listed = client.post("/api/review/declarations/query", json={"status": "pending"}, headers=headers)
        assert listed.status_code == 200
        item = listed.json()["groups"][0]
        assert (
            client.post(
                "/api/review/declarations/query", json={"pageSize": 1000}, headers=headers
            ).status_code
            == 400
        )
        bad = client.post(
            f"/api/review/declarations/{item['id']}/approve", json={"contentSha256": "x"}, headers=headers
        )
        assert bad.status_code == 400
        done = client.post(
            f"/api/review/declarations/{item['id']}/approve",
            json={"contentSha256": item["contentSha256"], "note": "接口审核"},
            headers=headers,
        )
        assert done.status_code == 200 and done.json()["review"]["status"] == "approved"
