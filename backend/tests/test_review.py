"""review 模块：列表状态与筛选（含出库准入、供应商）、整单与批量审核、冻结行（开票口径）、事件、幂等、来源变化、权限与回滚。

来源数据经 source 模块真实保存（SQLite 隔离库，合成 NS 数据）。
"""

from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.core.events import EventBus
from backend.modules.review.dto.review_dto import ApproveRequest, BatchApproveRequest, DeclarationListQuery
from backend.modules.review.public import ReviewApproved
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService, digest, snapshot
from backend.tests.test_source_storage import ACCOUNT, bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from fastapi.testclient import TestClient
from sqlalchemy import text

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
    save(ns, engine, bundle([], [customs("880")]))  # 没有关联子采购单：拉取时跳过，不入库
    return engine


def query(**values):
    return DeclarationListQuery(**values)


def group(service, record_no, status="all"):
    result = service.browse(query(status=status))
    return next(item for item in result.groups if item.recordNumber == record_no)


def clear_real_no(engine, record_no):
    """模拟 2026-10-23 前已入库、缺真实报关单号的旧数据（新拉取的不会再入库）。"""
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE source_customs_declarations SET declaration_no = NULL WHERE record_no = :r"),
            {"r": record_no},
        )
        # 旧数据入库时的摘要与当时内容一致：按清空后的内容重算，避免被"来源已变化"先行拦截
        identity = connection.execute(
            text("SELECT id FROM source_customs_declarations WHERE record_no = :r"), {"r": record_no}
        ).scalar()
        current = digest(snapshot(connection, identity))
        connection.execute(
            text("UPDATE source_customs_declarations SET content_sha256 = :d WHERE id = :i"),
            {"d": current, "i": identity},
        )
    return current


def other_supplier(order_id, customs_id):
    order_id, head, lines = purchase(order_id, customs_id)
    head["custrecord_swc_subpo_vendor"] = {"id": "78", "refName": "第二供应商"}
    return order_id, head, lines


def batch(service, items, note="批量核对", actor=USER):
    body = BatchApproveRequest(
        items=[{"id": item.id, "contentSha256": item.contentSha256} for item in items], note=note
    )
    return service.approve_batch(body, actor)


def approve(service, item, note="核对无误", actor=USER):
    return service.approve(int(item.id), ApproveRequest(contentSha256=item.contentSha256, note=note), actor)


def test_list_states_counts_and_purchase_basis(service, seeded, engine):
    result = service.browse(query())
    # CD880 没有关联子采购单，拉取时已跳过，不出现在核对列表
    assert result.counts == {
        "all": 1,
        "pending": 1,
        "approved": 0,
        "changed": 0,
        "approvedThisMonth": 0,
        "marginAlert": 0,
        "autoApprovable": 1,
        "customs": 2,
        "purchase": 2,
        "shown": 1,
    }
    assert [item.recordNumber for item in result.groups] == ["CD870"]
    assert rows(engine, "SELECT id FROM source_customs_declarations WHERE record_no = 'CD880'") == []
    assert result.accounts == [ACCOUNT]
    pending = group(service, "CD870")
    assert pending.review.allowed and pending.review.status == "pending"
    assert pending.customsCount == 2 and pending.purchaseCount == 2 and pending.unlinkedLines == []
    line = pending.customsLines[0].purchaseLines[0]
    assert (line.quantity, line.unit, line.amount) == ("10", "个", "100.5")  # 开票口径：采购数量与单位
    assert "报关数量 5 千克" in line.note
    assert pending.salesOrders == "SO1"  # 同一销售单在多个报关行出现，只在单头展示一次
    assert pending.company == "采购公司A"
    assert pending.customsLines[0].originPlace == "深圳"
    assert pending.customsLines[0].parent == ""  # 报关明细缺值时不能用子采购的 PO-100 补充
    # 关联完整、金额与币种齐全、申报幅度均已算出且不为负：可自动审核通过（只作预判，不自动写入）
    assert not pending.marginAlert and pending.autoReview.eligible, pending.autoReview.reasons
    assert [item.recordNumber for item in service.browse(query(status="auto")).groups] == ["CD870"]
    assert service.browse(query(status="margin_alert")).total == 0
    assert rows(engine, "SELECT id FROM review_records") == []


def test_negative_margin_is_alerted_and_not_auto_approvable(service, ns, engine):
    save(ns, engine, bundle([purchase(amounts=("99999.00", "99999.00"))], [customs("870")]))
    result = service.browse(query())
    assert result.counts["marginAlert"] == 1 and result.counts["autoApprovable"] == 0
    item = result.groups[0]
    assert item.marginAlert and not item.autoReview.eligible
    assert "申报幅度为负数（采购价高于申报价）" in item.autoReview.reasons
    assert [g.recordNumber for g in service.browse(query(status="margin_alert")).groups] == ["CD870"]


def test_customs_parent_and_origin_from_own_source(service, ns, engine):
    source = customs("870")
    source[2][0][1]["custrecord_swc_purachse_no"] = {
        "id": "407555",
        "refName": "采购订单 #YE-MQ260909-Y707",
    }
    source[2][0][1]["custrecord_swc_goods_place"] = {"id": "10", "refName": "深圳市"}
    source[2][1][1]["custrecord_swc_purachse_no"] = "采购订单 #SECOND"
    save(ns, engine, bundle([purchase()], [source]))
    current = group(service, "CD870")
    first, second = current.customsLines
    assert first.parent == "采购订单 #YE-MQ260909-Y707"
    assert first.originPlace == "深圳市"
    assert first.purchaseLines[0].parent == "PO-100"
    assert second.parent == "采购订单 #SECOND"


def test_customs_parent_internal_id_is_not_order_number(service, ns, engine):
    source = customs("870")
    source[2][0][1]["custrecord_swc_purachse_no"] = {"id": "407555"}
    save(ns, engine, bundle([purchase()], [source]))
    assert group(service, "CD870").customsLines[0].parent == ""


def test_status_filter_and_pagination(service, seeded, ns, engine):
    save(ns, engine, bundle([purchase("210", "890")], [customs("890")]))
    first = service.browse(query(pageSize=1, page=1))
    second = service.browse(query(pageSize=1, page=2))
    assert first.total == 2 and first.pages == 2 and len(first.groups) == len(second.groups) == 1
    assert first.groups[0].id != second.groups[0].id
    assert service.browse(query(keyword="CD880")).total == 0
    with pytest.raises(ValueError):
        query(status="unshipped")  # 未出库不再作为列表筛选项


def test_legacy_row_without_real_number_is_hidden_and_refused(service, seeded, engine):
    item = group(service, "CD870")
    item = item.model_copy(update={"contentSha256": clear_real_no(engine, "CD870")})
    assert service.browse(query()).counts["all"] == 0
    with pytest.raises(ApiError, match="缺少真实报关单号") as error:
        approve(service, item)
    assert error.value.status == 409
    assert rows(engine, "SELECT id FROM review_records") == []


def test_supplier_filter_and_options(service, seeded, ns, engine):
    save(ns, engine, bundle([other_supplier("210", "890")], [customs("890")]))
    result = service.browse(query())
    names = {option.name for option in result.suppliers}
    assert names == {"上海 供应商（有限）公司", "第二供应商"}
    second = next(option for option in result.suppliers if option.name == "第二供应商")
    filtered = service.browse(query(supplierId=second.id))
    assert [item.recordNumber for item in filtered.groups] == ["CD890"] and filtered.total == 1
    assert filtered.counts["all"] == 1  # 计数随供应商条件变化
    assert service.browse(query(supplierId="999999")).total == 0
    with pytest.raises(ValueError):
        query(supplierId="abc")


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
    counts = service.browse(query()).counts
    assert counts["approved"] == 1 and counts["approvedThisMonth"] == 1  # 刚审核的计入本月


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
    assert service.browse(query()).counts["changed"] == 1  # 概况卡「来源变化需重审」
    result = approve(service, changed, note="重新审核")
    assert result.review.revision == 2 and result.review.status == "approved"
    statuses = [
        (r["revision"], r["status"]) for r in rows(engine, "SELECT * FROM review_records ORDER BY revision")
    ]
    assert statuses == [(1, "superseded"), (2, "active")]
    assert received[1].superseded_review_id == received[0].review_id


def test_batch_approve_reports_each_declaration(service, seeded, ns, engine, received):
    save(ns, engine, bundle([purchase("210", "890")], [customs("890")]))
    save(ns, engine, bundle([purchase("220", "891")], [customs("891")]))
    first, second, unshipped = group(service, "CD870"), group(service, "CD890"), group(service, "CD891")
    unshipped = unshipped.model_copy(update={"contentSha256": clear_real_no(engine, "CD891")})
    # 页面打开后 CD890 来源变化：该张被跳过，其余照常通过
    save(ns, engine, bundle([purchase("210", "890", amounts=("99.00", "20.00"))], [customs("890")]))
    result = batch(service, [first, second, unshipped])
    assert [item.recordNumber for item in result.approved] == ["CD870"]
    skipped = {item.id: item.reason for item in result.skipped}
    assert "来源已变化" in skipped[second.id] and "未出库" in skipped[unshipped.id]
    assert len(received) == 1 and received[0].customs_declaration_id == int(first.id)
    records = rows(engine, "SELECT customs_declaration_id, note FROM review_records")
    assert records == [{"customs_declaration_id": int(first.id), "note": "批量核对"}]
    again = batch(service, [first])  # 同一内容重复提交：不重复审核
    assert [item.id for item in again.approved] == [first.id] and len(received) == 1


def test_batch_approve_validation_and_identity(service, seeded):
    item = group(service, "CD870")
    with pytest.raises(ApiError) as error:
        batch(service, [item], actor="service:feishu")
    assert error.value.status == 403
    entry = {"id": item.id, "contentSha256": item.contentSha256}
    with pytest.raises(ValueError, match="重复"):
        BatchApproveRequest(items=[entry, entry])
    with pytest.raises(ValueError):
        BatchApproveRequest(items=[])
    with pytest.raises(ValueError):
        BatchApproveRequest(items=[{**entry, "id": str(i + 1)} for i in range(51)])


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
    app = create_app(context.settings, context.ns, engine)
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
        path = "/api/review/declarations/approve-batch"
        assert client.post(path, json={"items": []}, headers=headers).status_code == 400
        repeated = client.post(
            path,
            json={"items": [{"id": item["id"], "contentSha256": item["contentSha256"]}]},
            headers=headers,
        )
        assert repeated.status_code == 200 and repeated.json()["approved"][0]["id"] == item["id"]
