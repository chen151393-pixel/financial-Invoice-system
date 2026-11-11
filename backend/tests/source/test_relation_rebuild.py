"""已存快照直接重建旧关联：无需 NS，同事务排队财务快照，失败回滚与重启幂等。"""

from copy import deepcopy

import pytest
from backend.app import create_events
from backend.core.events import EventBus
from backend.modules.review.dto.review_dto import DeclarationListQuery
from backend.modules.review.service.calculation_service import CalculationService
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService, SourceChanged
from backend.modules.source.service import link_service
from backend.modules.source.service.relation_rebuild_service import RelationRebuildService
from backend.modules.source.service.relation_rebuild_worker import RelationRebuildWorker
from backend.tests.source.test_summary_line_relations import films as films
from backend.tests.test_source_storage import declaration, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import text


def seed_old(ns, engine, films, monkeypatch):
    data = deepcopy(films)
    data["relation_evidence"]["870"]["rawLines"] = []
    with monkeypatch.context() as patch:
        patch.setattr(link_service, "local_line_relations", lambda *a, **kw: {})
        patch.setattr(link_service, "LOCAL_RELATION_VERSION", "old")
        save(ns, engine, data)


def test_rebuild_old_saved_data_refreshes_review_and_is_idempotent(ns, engine, films, monkeypatch):
    seed_old(ns, engine, films, monkeypatch)
    events = create_events()
    review = ReviewService(engine, DeclarationService(engine), events)
    calculations = CalculationService(review)
    calculations.rebuild()
    assert len(review.browse(DeclarationListQuery()).groups[0].unlinkedLines) == 2
    original_head = declaration(engine)
    original_purchases = rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY id")
    rebuild = RelationRebuildService(engine, events)
    result = rebuild.rebuild(record_no="CD870", account="prod")
    assert len(result) == 1 and result[0]["changed"] is True
    assert result[0]["linkedLines"] == 2 and result[0]["unlinkedLines"] == 0
    assert declaration(engine)["synced_at"] == original_head["synced_at"]
    assert declaration(engine)["raw_record_id"] == original_head["raw_record_id"]
    assert rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY id") == original_purchases
    assert calculations.pending()  # 事件在同一事务排队；页面不会永久保留旧结果。
    calculations.rebuild()
    group = review.browse(DeclarationListQuery()).groups[0]
    assert group.unlinkedLines == []
    assert [row.purchaseLines[0].quantity for row in group.customsLines] == ["8000", "512"]
    assert [row.purchaseLines[0].amount for row in group.customsLines] == ["51920", "36700.16"]
    before = rows(engine, "SELECT * FROM source_customs_purchase_links ORDER BY id")
    raw_count = rows(engine, "SELECT count(*) AS n FROM source_raw_records")
    assert rebuild.rebuild()[0]["status"] == "current"
    assert rows(engine, "SELECT * FROM source_customs_purchase_links ORDER BY id") == before
    assert rows(engine, "SELECT count(*) AS n FROM source_raw_records") == raw_count
    assert calculations.pending() == []
    assert rows(engine, "SELECT id FROM review_records") == []


def test_event_failure_rolls_back_links_digest_and_version(ns, engine, films, monkeypatch):
    seed_old(ns, engine, films, monkeypatch)
    before = declaration(engine)
    raw_count = rows(engine, "SELECT count(*) AS n FROM source_raw_records")
    events = EventBus()

    def fail(connection, event):
        raise RuntimeError("queue failure")

    events.subscribe(SourceChanged, fail)
    with pytest.raises(RuntimeError, match="queue failure"):
        RelationRebuildService(engine, events).rebuild()
    assert declaration(engine) == before
    assert rows(engine, "SELECT count(*) AS n FROM source_raw_records") == raw_count
    assert len(rows(engine, "SELECT * FROM source_customs_purchase_links WHERE status='active'")) == 1
    assert RelationRebuildService(engine, create_events()).rebuild()[0]["changed"] is True


def test_rebuild_scopes_and_source_dependency_guard(ns, engine, films, monkeypatch):
    seed_old(ns, engine, films, monkeypatch)
    rebuild = RelationRebuildService(engine, create_events())
    assert rebuild.rebuild(record_no="CD999") == []
    assert rebuild.rebuild(account="other-account") == []
    with engine.begin() as connection:
        from backend.modules.source.entity import customs_declarations

        connection.execute(
            customs_declarations.update().values(relation_issues=[link_service.DEPENDENCY_ISSUE])
        )
    result = rebuild.rebuild()
    assert result[0]["status"] == "skipped"
    assert len(rows(engine, "SELECT * FROM source_customs_purchase_links WHERE status='active'")) == 1


def test_startup_worker_rebuilds_persisted_old_links(ns, engine, films, monkeypatch):
    seed_old(ns, engine, films, monkeypatch)
    worker = RelationRebuildWorker(RelationRebuildService(engine, create_events()))
    worker.start()
    worker.thread.join(timeout=10)
    try:
        assert not worker.thread.is_alive()
        assert len(rows(engine, "SELECT * FROM source_customs_purchase_links WHERE status='active'")) == 3
    finally:
        worker.stop()


def test_missing_local_evidence_does_not_destroy_existing_links(ns, engine, films):
    save(ns, engine, films)
    before = rows(engine, "SELECT * FROM source_customs_purchase_links ORDER BY id")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM source_raw_records WHERE record_type='relation_evidence'"))
    result = RelationRebuildService(engine, create_events()).rebuild()
    assert result[0]["status"] == "skipped"
    assert rows(engine, "SELECT * FROM source_customs_purchase_links ORDER BY id") == before


def test_authenticated_rebuild_endpoint_never_reads_ns(context, ns, engine, films, monkeypatch):
    from backend.app import create_app
    from fastapi.testclient import TestClient

    seed_old(ns, engine, films, monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("本地重建不能请求 NS")

    monkeypatch.setattr(context.ns, "request", forbidden)
    app = create_app(context.settings, context.ns, engine)
    client = TestClient(app)  # 不启用其他业务后台线程，仅验证真实应用装配和身份依赖。
    headers = {"Authorization": f"Bearer {context.settings.service_key}"}
    try:
        assert client.post("/api/source/relations/rebuild", json={"recordNo": "CD870"}).status_code == 401
        assert client.post("/api/source/relations/rebuild", json={}, headers=headers).status_code == 400
        response = client.post(
            "/api/source/relations/rebuild", json={"recordNo": "CD870", "account": "prod"}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"][0]["unlinkedLines"] == 0
    finally:
        client.close()
