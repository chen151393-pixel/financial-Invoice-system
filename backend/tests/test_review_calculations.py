"""后台财务计算、代次一致性、重试、SQL 分页及来源汇率联动。"""

import re
from copy import deepcopy
from decimal import Decimal

import pytest
from backend.app import create_events
from backend.core.events import EventBus
from backend.modules.review.dao import calculation_job_dao
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.service.calculation_service import CalculationService, now_utc
from backend.modules.review.service.calculation_worker import CalculationWorker
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService
from backend.tests.review_helpers import comparable_purchase as purchase
from backend.tests.test_source_storage import ACCOUNT, bundle, customs, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import event, text


@pytest.fixture
def review(engine):
    return ReviewService(engine, DeclarationService(engine), create_events())


def query(**kwargs):
    return DeclarationListQuery(**kwargs)


def seed(ns, engine):
    save(ns, engine, bundle([purchase()], [customs("870")]))


def test_sync_only_queues_and_restart_computes_existing_rows(review, ns, engine, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("同步请求不能直接计算财务幅度")

    with monkeypatch.context() as patch:
        patch.setattr(review, "build_declarations", forbidden)
        seed(ns, engine)
    assert rows(engine, "SELECT id FROM review_declaration_snapshots") == []
    assert len(rows(engine, "SELECT ns_account FROM review_calculation_jobs")) == 1
    pending = review.browse(query())
    assert pending.groups == [] and "后台计算中" in pending.notices[0]
    # 模拟首次部署的旧数据：没有计算队列，由初始化发现并补建。
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM review_calculation_jobs"))
    calculations = CalculationService(review)
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    result = review.browse(query())
    assert result.total == 1 and result.groups[0].calculationStatus == "ready"
    assert result.groups[0].calculatedAt
    assert not result.notices
    assert rows(engine, "SELECT id FROM review_records") == []
    assert calculations.pending() == []
    calculations.initialize()  # 同版本重启不能每次全量补算。
    assert calculations.pending() == []


def test_list_uses_only_four_review_queries_with_sql_pagination(review, ns, engine, monkeypatch):
    seed(ns, engine)
    save(ns, engine, bundle([purchase("201", "871")], [customs("871")]))
    CalculationService(review).rebuild()

    def forbidden(*args, **kwargs):
        raise AssertionError("列表不得读取来源或重算幅度")

    monkeypatch.setattr(review.declarations, "details", forbidden)
    monkeypatch.setattr(review.declarations, "index", forbidden)
    monkeypatch.setattr(review, "build_declarations", forbidden)
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        page = review.browse(query(page=2, pageSize=1))
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert page.total == 2 and page.pages == 2
    assert [g.recordNumber for g in page.groups] == ["CD870"]
    assert len(statements) == 4
    assert not any(re.search(r"(?:FROM|JOIN) source_", s) or "raw_records" in s for s in statements)
    assert any("LIMIT" in s and "OFFSET" in s for s in statements)
    supplier = page.suppliers[0].id
    assert review.browse(query(supplierId=supplier, keyword="SUB-201")).total == 1
    assert review.browse(query(keyword="清洗液")).total == 2
    assert review.browse(query(account="missing")).total == 0


def test_dirty_results_cannot_advertise_auto_review(review, ns, engine):
    seed(ns, engine)
    calculations = CalculationService(review)
    calculations.rebuild()
    assert review.browse(query()).groups[0].autoReview.eligible
    save(ns, engine, bundle([purchase(amounts=("99999", "20"))], [customs("870")]))
    dirty = review.browse(query())
    assert dirty.notices and dirty.counts["autoApprovable"] == 0
    group = dirty.groups[0]
    assert group.calculationStatus == "pending"
    assert not group.autoReview.eligible and not group.review.allowed
    assert all(line.marginStatus == "unavailable" and not line.margin for line in group.customsLines)
    assert review.browse(query(status="auto")).total == 0
    CalculationWorker(calculations).run_once()
    refreshed = review.browse(query(status="margin_alert"))
    assert refreshed.total == 1 and refreshed.groups[0].marginAlert


def test_update_during_calculation_discards_old_generation(review, ns, engine, monkeypatch):
    seed(ns, engine)
    calculations = CalculationService(review)
    calculations.rebuild()
    before = rows(engine, "SELECT payload FROM review_declaration_snapshots")
    seed(ns, engine)
    build = calculations.build

    def concurrent_update(account):
        result = build(account)
        save(ns, engine, bundle([purchase(amounts=("99999", "20"))], [customs("870")]))
        return result

    monkeypatch.setattr(calculations, "build", concurrent_update)
    assert calculations.calculate(calculations.pending()[0]) is False
    assert rows(engine, "SELECT payload FROM review_declaration_snapshots") == before
    monkeypatch.setattr(calculations, "build", build)
    assert calculations.calculate(calculations.pending()[0]) is True
    assert review.browse(query()).groups[0].marginAlert


def test_failure_retains_snapshot_and_retries_after_restart(review, ns, engine, monkeypatch):
    seed(ns, engine)
    calculations = CalculationService(review)
    calculations.rebuild()
    seed(ns, engine)

    def fail(account):
        raise RuntimeError("合成计算失败")

    with monkeypatch.context() as patch:
        patch.setattr(calculations, "build", fail)
        CalculationWorker(calculations).run_once()
    group = review.browse(query()).groups[0]
    assert group.calculationStatus == "failed" and not group.autoReview.eligible
    assert calculations.pending() == []  # 持久化退避，不能忙循环。
    with engine.begin() as connection:
        connection.execute(text("UPDATE review_calculation_jobs SET retry_at=NULL"))
    CalculationWorker(CalculationService(review)).run_once()
    assert review.browse(query()).groups[0].calculationStatus == "ready"


def test_changed_tolerance_rebuilds_and_hides_old_precheck(review, ns, engine):
    save(ns, engine, bundle([purchase(amounts=("107.50", "20"))], [customs("870")]))
    CalculationService(review).rebuild()
    assert review.browse(query()).groups[0].autoReview.eligible
    strict = ReviewService(engine, DeclarationService(engine), EventBus(), Decimal("0.05"))
    assert not strict.browse(query()).groups[0].autoReview.eligible
    changed = CalculationService(strict)
    changed.initialize()
    CalculationWorker(changed).run_once()
    assert strict.browse(query()).groups[0].marginAlert
    assert CalculationService(review).calculate({"ns_account": ACCOUNT}) is False


def test_approval_enqueues_and_does_not_wait_for_account_rebuild(review, ns, engine):
    seed(ns, engine)
    calculations = CalculationService(review)
    calculations.rebuild()
    item = review.browse(query()).groups[0]
    result = review.approve(int(item.id), ApproveRequest(contentSha256=item.contentSha256), "user:admin")
    assert result.review.status == "approved"
    assert calculations.pending()
    CalculationWorker(calculations).run_once()
    page = review.browse(query(status="approved"))
    assert page.total == 1 and page.counts["approvedThisMonth"] == 1


def test_shared_sales_rate_refreshes_other_declarations_without_reapproval(review, ns, engine):
    seed(ns, engine)
    save(ns, engine, bundle([purchase("201", "871")], [customs("871")]))
    calculations = CalculationService(review)
    calculations.rebuild()
    item = next(g for g in review.browse(query()).groups if g.recordNumber == "CD870")
    review.approve(int(item.id), ApproveRequest(contentSha256=item.contentSha256), "user:admin")
    CalculationWorker(calculations).run_once()
    before = review.browse(query(status="approved")).groups[0]
    update = deepcopy(bundle([purchase("201", "871")], [customs("871")]))
    update["sales_orders"]["90"]["exchangerate"] = "3.5"
    save(ns, engine, update)
    CalculationWorker(calculations).run_once()
    after = review.browse(query(status="approved")).groups[0]
    assert after.id == before.id and after.contentSha256 == before.contentSha256
    assert after.review.revision == before.review.revision
    assert after.customsLines[0].declaredUnitPriceCny != before.customsLines[0].declaredUnitPriceCny
    assert len(rows(engine, "SELECT id FROM review_records")) == 1


def test_missing_sales_rate_persists_unavailable(review, ns, engine):
    data = deepcopy(bundle([purchase()], [customs("870")]))
    data["sales_orders"]["90"]["exchangerate"] = None
    save(ns, engine, data)
    CalculationService(review).rebuild()
    item = review.browse(query()).groups[0]
    assert item.calculationStatus == "ready" and not item.marginAlert and not item.autoReview.eligible
    assert item.customsLines[0].marginStatus == "unavailable"


def test_queue_request_rolls_back_with_source_transaction(review, ns, engine):
    seed(ns, engine)
    before = rows(engine, "SELECT requested_revision FROM review_calculation_jobs")
    with pytest.raises(RuntimeError), engine.begin() as connection:
        calculation_job_dao.request(connection, ACCOUNT, now_utc())
        raise RuntimeError("合成事务回滚")
    assert rows(engine, "SELECT requested_revision FROM review_calculation_jobs") == before


def test_failed_publication_rolls_back_snapshot_and_generation(review, ns, engine, monkeypatch):
    seed(ns, engine)
    calculations = CalculationService(review)
    calculations.rebuild()
    original = rows(engine, "SELECT payload FROM review_declaration_snapshots")
    seed(ns, engine)

    def fail(*args):
        raise RuntimeError("合成发布失败")

    monkeypatch.setattr(calculation_job_dao, "complete", fail)
    with pytest.raises(RuntimeError, match="合成发布失败"):
        calculations.calculate(calculations.pending()[0])
    assert rows(engine, "SELECT payload FROM review_declaration_snapshots") == original
    assert calculations.pending()


def test_busy_ledger_defers_without_failure_or_rebuild(review, ns, engine, monkeypatch):
    """账本被同步等写入占用时只推迟重算：不记失败、不显示失败、不在两秒循环里反复整账套重算。"""
    from backend.core import named_lock, write_lock

    seed(ns, engine)
    calculations = CalculationService(review)
    built = []
    ledger = write_lock.ledger_name(engine)
    acquire = named_lock.acquire

    def busy(connection, name, timeout=0):
        return False if name == ledger else acquire(connection, name, timeout)

    with monkeypatch.context() as patch:
        patch.setattr(named_lock, "acquire", busy)
        patch.setattr(calculations, "build", lambda account: built.append(account))
        CalculationWorker(calculations).run_once()
    job = rows(engine, "SELECT attempts, last_error, retry_at FROM review_calculation_jobs")[0]
    assert built == [] and job["attempts"] == 0 and job["last_error"] == ""
    assert job["retry_at"] is not None and calculations.pending() == []
    notices = " ".join(review.browse(query()).notices)
    assert "后台计算中" in notices and "计算失败" not in notices
    with engine.begin() as connection:
        connection.execute(text("UPDATE review_calculation_jobs SET retry_at=NULL"))
    CalculationWorker(calculations).run_once()
    assert review.browse(query()).groups[0].calculationStatus == "ready"


def test_split_bulk_search_uses_snapshot_fields_and_filtered_counts(review, ns, engine, monkeypatch):
    seed(ns, engine)
    save(ns, engine, bundle([purchase("201", "871")], [customs("871")]))
    CalculationService(review).rebuild()
    supplier = review.browse(query()).suppliers[0].name

    def forbidden(*args, **kwargs):
        raise AssertionError("搜索必须使用快照，不能读取实时来源")

    monkeypatch.setattr(review.declarations, "details", forbidden)
    both = review.browse(query(recordNo="CD870，CD871;CD870", pageSize=1, page=2))
    assert both.total == 2 and both.counts["all"] == 2 and both.pages == 2
    assert len(both.groups) == 1
    found = review.browse(
        query(supplierName="不存在;" + supplier, recordNo="870,871", purchaseOrderNo="不存在\nSUB-201")
    )
    assert found.total == 1 and found.counts["all"] == 1
    assert found.groups[0].recordNumber == "CD871"
    assert review.browse(query(recordNo="870", purchaseOrderNo="SUB-201")).total == 0
    assert review.browse(query(recordNo="SUB-201")).total == 0
    assert review.browse(query(purchaseOrderNo="清洗液")).total == 0
    assert review.browse(query(supplierName="不存在")).total == 0
    for field in ("supplierName", "recordNo", "purchaseOrderNo"):
        assert review.browse(query(**{field: "%"})).total == 0
    assert review.browse(query(recordNo="，；\n ")).total == 2


def test_bulk_input_limits_and_literal_spaces():
    from backend.core.search_terms import search_terms
    from pydantic import ValidationError

    assert search_terms(" ACME LTD，乙; ACME LTD\n丙 ") == ("ACME LTD", "乙", "丙")
    assert query(recordNo=";".join(str(i) for i in range(50))).recordNo
    for value in ("x" * 121, ";".join(str(i) for i in range(51)), "x" * 6501):
        with pytest.raises(ValidationError):
            query(recordNo=value)
