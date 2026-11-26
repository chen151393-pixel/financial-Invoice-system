"""后台财务计算、代次一致性、重试、SQL 分页及来源汇率联动。"""

import json
import re
from copy import deepcopy
from decimal import Decimal

import pytest
from backend.app import create_events
from backend.core.events import EventBus
from backend.modules.identity.dao import user_dao
from backend.modules.review.dao import calculation_job_dao
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.service.calculation_service import CalculationService, now_utc
from backend.modules.review.service.calculation_worker import CalculationWorker
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService
from backend.tests.review_helpers import comparable_purchase as purchase
from backend.tests.review_helpers import customs_prices as customs
from backend.tests.test_source_storage import ACCOUNT, bundle, rows, save
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


def test_list_paginates_before_batching_live_approval_progress(review, ns, engine, monkeypatch):
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
        page_statements = statements.copy()
        statements.clear()
        wide_page = review.browse(query(pageSize=2))
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert page.total == 2 and page.pages == 2
    assert [g.recordNumber for g in page.groups] == ["CD870"]
    assert len(wide_page.groups) == 2
    # 同样的业务状态下，扩大页容量不会逐行增加查询；来源只读单头。
    # 另有一条海关当前回执审核引用查询；没有已审核回执时不额外读取来源。
    assert len(page_statements) == len(statements) == 8
    source_reads = [s for s in statements if re.search(r"(?:FROM|JOIN) source_", s)]
    assert len(source_reads) == 1 and "FROM source_customs_declarations" in source_reads[0]
    assert "WHERE source_customs_declarations.declaration_no IN" in source_reads[0]
    assert any("LIMIT" in s and "OFFSET" in s for s in page_statements)
    supplier = page.suppliers[0].id
    assert review.browse(query(supplierId=supplier, keyword="SUB-201")).total == 1
    assert review.browse(query(keyword="清洗液")).total == 2
    assert review.browse(query(account="missing")).total == 0


def test_list_resolves_historical_reviewer_from_the_local_directory(review, ns, engine):
    seed(ns, engine)
    calculations = CalculationService(review)
    calculations.rebuild()
    item = review.browse(query()).groups[0]
    actor = "user:fs:finance-reviewer"
    review.approve(int(item.id), ApproveRequest(contentSha256=item.contentSha256), actor)
    calculations.rebuild()

    historical = review.browse(query(status="approved")).groups[0].review
    assert historical.reviewedBy == historical.reviewedByName == actor

    with engine.begin() as connection:
        user_dao.save(
            connection,
            {
                "user_id": "finance-reviewer",
                "open_id": None,
                "union_id": None,
                "name": "张三",
                "avatar_url": None,
                "active": False,
                "inactive_reason": "已离职",
            },
            now_utc(),
        )

    resolved = review.browse(query(status="approved")).groups[0].review
    assert resolved.reviewedBy == actor
    assert resolved.reviewedByName == "张三"


def test_dirty_results_cannot_advertise_auto_review(review, ns, engine):
    seed(ns, engine)
    calculations = CalculationService(review)
    calculations.rebuild()
    assert review.browse(query()).groups[0].autoReview.eligible
    save(ns, engine, bundle([purchase(amounts=("226", "20"))], [customs("870", original="3")]))
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
        save(ns, engine, bundle([purchase(amounts=("226", "20"))], [customs("870", original="3")]))
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
    save(
        ns,
        engine,
        bundle(
            [purchase(amounts=("121.475", "20.00"))],
            [customs("870", original="12.1475", declared="10.65", currency="CNY")],
        ),
    )
    CalculationService(review).rebuild()
    assert review.browse(query()).groups[0].autoReview.eligible
    strict = ReviewService(engine, DeclarationService(engine), EventBus(), Decimal("0.05"))
    assert not strict.browse(query()).groups[0].autoReview.eligible
    changed = CalculationService(strict)
    changed.initialize()
    CalculationWorker(changed).run_once()
    assert strict.browse(query()).groups[0].marginAlert
    assert CalculationService(review).calculate({"ns_account": ACCOUNT}) is False


def test_v6_purchase_snapshot_is_hidden_then_rebuilt_with_customs_prices(review, ns, engine):
    seed(ns, engine)
    calculations = CalculationService(review)
    calculations.rebuild()
    snapshot = rows(engine, "SELECT id,payload FROM review_declaration_snapshots")[0]
    payload = json.loads(snapshot["payload"])
    for line in payload["customsLines"]:
        line.pop("originalUnitPriceCny")
        line.pop("originalPriceUnit")
        line.pop("declaredPriceUnit")
        line.update(combinedPurchaseUnitPrice="16.142857", margin="-12.31%", marginStatus="negative")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_declaration_snapshots SET payload=:p,margin_alert=1 WHERE id=:i"),
            {"p": json.dumps(payload), "i": snapshot["id"]},
        )
        connection.execute(text("UPDATE review_calculation_jobs SET calculation_key='review-v6:cny=0.10'"))
    stale = review.browse(query())
    assert stale.counts["marginAlert"] == 0
    line = stale.groups[0].customsLines[0]
    assert line.marginStatus == "unavailable" and line.margin == line.originalUnitPriceCny == ""
    assert line.originalPrice == line.purchaseUnitPriceUsd == line.declaredUnitPriceUsd == ""
    assert "后台计算中" in line.purchasePriceNote
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    fresh = review.browse(query()).groups[0]
    assert fresh.calculationStatus == "ready" and not fresh.marginAlert
    assert fresh.contentSha256 == payload["contentSha256"]
    line = fresh.customsLines[0]
    assert (
        line.margin == "16.49%"
        and line.originalUnitPriceCny == "8.894"
        and line.declaredUnitPriceCny == "10.65"
    )
    assert "combinedPurchaseUnitPrice" not in line.model_dump()
    assert rows(engine, "SELECT id FROM review_records") == []


def test_v18_zero_amount_snapshot_rebuilds_with_zero_purchase_price(review, ns, engine):
    save(ns, engine, bundle([purchase(amounts=("0", "0"))], [customs("870")]))
    calculations = CalculationService(review)
    calculations.rebuild()
    snapshot = rows(engine, "SELECT id,payload FROM review_declaration_snapshots")[0]
    payload = json.loads(snapshot["payload"])
    for line in payload["customsLines"]:
        line.update(
            purchaseUnitPriceUsd="",
            originalPrice="",
            originalUnitPriceCny="",
            purchasePriceNote="采购含税金额缺失或非正数，无法计算采购单价",
            margin="",
            marginStatus="unavailable",
        )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_declaration_snapshots SET payload=:p WHERE id=:i"),
            {"p": json.dumps(payload), "i": snapshot["id"]},
        )
        connection.execute(text("UPDATE review_calculation_jobs SET calculation_key='review-v18:cny=0.10'"))
    assert review.browse(query()).groups[0].calculationStatus == "pending"
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    fresh = review.browse(query()).groups[0]
    assert fresh.calculationStatus == "ready" and fresh.contentSha256 == payload["contentSha256"]
    for line in fresh.customsLines:
        assert line.purchaseUnitPriceUsd == line.originalPrice == line.originalUnitPriceCny == "0"
        assert line.marginStatus == "ok" and line.margin == "100.00%"
    assert rows(engine, "SELECT id FROM review_records") == []
    assert rows(engine, "SELECT amount FROM source_purchase_order_lines") == [
        {"amount": 0},
        {"amount": 0},
    ]


def test_v15_original_unit_mismatch_rebuilds_with_actual_purchase_units(review, ns, engine):
    declaration = customs("870")
    for _, source in declaration[2]:
        source.update(custrecord_swc_unit="千克", custrecord_swc_quantity=Decimal("5"))
    save(ns, engine, bundle([purchase()], [declaration]))
    calculations = CalculationService(review)
    calculations.rebuild()
    snapshot = rows(engine, "SELECT id,payload FROM review_declaration_snapshots")[0]
    payload = json.loads(snapshot["payload"])
    for line in payload["customsLines"]:
        line.update(
            margin="",
            marginStatus="unit_mismatch",
            marginNote="原始单位“千克”与报关单位“个”不一致，不计算申报幅度",
        )
    payload["unitMismatch"] = True
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_declaration_snapshots SET payload=:p WHERE id=:i"),
            {"p": json.dumps(payload), "i": snapshot["id"]},
        )
        connection.execute(text("UPDATE review_calculation_jobs SET calculation_key='review-v15:cny=0.10'"))
    stale = review.browse(query())
    assert stale.groups[0].calculationStatus == "pending"
    assert stale.counts["unitMismatch"] == stale.counts["autoApprovable"] == 0
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    refreshed = review.browse(query())
    fresh = refreshed.groups[0]
    assert fresh.calculationStatus == "ready" and fresh.autoReview.eligible
    assert not fresh.unitMismatch and not fresh.quantityMismatch
    assert fresh.contentSha256 == payload["contentSha256"]
    assert all(line.marginStatus == "ok" and line.margin for line in fresh.customsLines)
    assert refreshed.counts["unitMismatch"] == 0
    assert rows(engine, "SELECT id FROM review_records") == []
    assert rows(engine, "SELECT id FROM review_lines") == []


def test_v16_child_unit_snapshot_rebuilds_with_parent_purchase_unit(review, ns, engine):
    data = bundle([purchase()], [customs("870")])
    for parent in data["relation_evidence"]["870"]["parentLines"]:
        parent["unitname"] = "包"
    save(ns, engine, data)
    calculations = CalculationService(review)
    calculations.rebuild()
    snapshot = rows(engine, "SELECT id,payload FROM review_declaration_snapshots")[0]
    payload = json.loads(snapshot["payload"])
    for line in payload["customsLines"]:
        line.update(originalPriceUnit="个", margin="10.00%", marginStatus="ok", marginNote="")
    payload["unitMismatch"] = False
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_declaration_snapshots SET payload=:p WHERE id=:i"),
            {"p": json.dumps(payload), "i": snapshot["id"]},
        )
        connection.execute(text("UPDATE review_calculation_jobs SET calculation_key='review-v16:cny=0.10'"))
    stale = review.browse(query())
    assert stale.groups[0].calculationStatus == "pending" and stale.counts["autoApprovable"] == 0
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    fresh = review.browse(query()).groups[0]
    assert fresh.calculationStatus == "ready" and fresh.unitMismatch and not fresh.autoReview.eligible
    assert all(
        line.originalPriceUnit == "包" and line.marginStatus == "unit_mismatch" for line in fresh.customsLines
    )
    assert fresh.contentSha256 == payload["contentSha256"]
    assert rows(engine, "SELECT id FROM review_records") == []


def test_v9_snapshot_rebuilds_purchase_price_without_changing_review_basis(review, ns, engine):
    order = purchase()
    for _, row in order[2]:
        row.update(
            custrecord_swc_subpo_item_bgqty=Decimal("17687.33"),
            custrecord_swc_subpo_item_amountwithtax=Decimal("242310.6"),
        )
    save(ns, engine, bundle([order], [customs("870")]))
    calculations = CalculationService(review)
    calculations.rebuild()
    snapshot = rows(engine, "SELECT payload FROM review_declaration_snapshots")[0]
    payload = json.loads(snapshot["payload"])
    for line in payload["customsLines"]:
        for child in line["purchaseLines"]:
            child["price"] = "23.45"
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_declaration_snapshots SET payload=:p"),
            {"p": json.dumps(payload)},
        )
        connection.execute(text("UPDATE review_calculation_jobs SET calculation_key='review-v9:cny=0.10'"))
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    fresh = review.browse(query()).groups[0]
    assert fresh.calculationStatus == "ready"
    assert fresh.contentSha256 == payload["contentSha256"]
    assert all(child.price == "13.70" for line in fresh.customsLines for child in line.purchaseLines)
    assert rows(engine, "SELECT id FROM review_records") == []


def test_v12_tax_inclusive_snapshot_rebuilds_margin_counts_and_keeps_approval(review, ns, engine):
    save(
        ns,
        engine,
        bundle(
            [purchase(amounts=("1130", "1130"))],
            [customs("870", original="113", declared="100", currency="CNY")],
        ),
    )
    calculations = CalculationService(review)
    calculations.rebuild()
    initial = review.browse(query()).groups[0]
    review.approve(int(initial.id), ApproveRequest(contentSha256=initial.contentSha256), "user:admin")
    CalculationWorker(calculations).run_once()
    before = rows(engine, "SELECT * FROM review_records")
    frozen = rows(engine, "SELECT * FROM review_lines")
    snapshot = rows(engine, "SELECT payload FROM review_declaration_snapshots")[0]
    payload = json.loads(snapshot["payload"])
    payload["marginAlert"] = True
    for line in payload["customsLines"]:
        line.update(margin="-13.00%", marginStatus="negative", originalUnitPriceCny="113")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_declaration_snapshots SET payload=:p,margin_alert=1"),
            {"p": json.dumps(payload)},
        )
        connection.execute(text("UPDATE review_calculation_jobs SET calculation_key='review-v12:cny=0.10'"))
    stale = review.browse(query())
    assert stale.groups[0].calculationStatus == "pending"
    assert stale.groups[0].customsLines[0].originalUnitPriceCny == ""
    assert stale.counts["marginAlert"] == stale.counts["autoApprovable"] == 0
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    refreshed = review.browse(query())
    fresh = refreshed.groups[0]
    assert fresh.calculationStatus == "ready" and fresh.review.status == "approved"
    assert fresh.contentSha256 == initial.contentSha256 and not fresh.marginAlert
    assert refreshed.counts["marginAlert"] == 0
    for line in fresh.customsLines:
        assert line.originalPrice == "14.084507"
        assert line.originalUnitPriceCny == line.declaredUnitPriceCny == "100"
        assert line.margin == "0.00%" and line.marginStatus == "ok" and line.marginNote == ""
    assert review.browse(query(status="margin_alert")).total == 0
    assert rows(engine, "SELECT * FROM review_records") == before
    assert rows(engine, "SELECT * FROM review_lines") == frozen


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


def test_v13_unavailable_snapshot_rebuilds_as_quantity_mismatch(review, ns, engine):
    order = purchase()
    for _, row in order[2]:
        row["custrecord_swc_subpo_item_bgqty"] = Decimal("9")
    save(ns, engine, bundle([order], [customs("870", original="3")]))
    calculations = CalculationService(review)
    calculations.rebuild()
    snapshot = rows(engine, "SELECT id,payload FROM review_declaration_snapshots")[0]
    payload = json.loads(snapshot["payload"])
    for line in payload["customsLines"]:
        line.update(
            margin="", marginStatus="unavailable", marginNote="数量不一致（报关行 10，子采购报关合计 9）"
        )
    payload["quantityMismatch"] = False
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_declaration_snapshots SET payload=:p,margin_alert=0"),
            {"p": json.dumps(payload)},
        )
        connection.execute(text("UPDATE review_calculation_jobs SET calculation_key='review-v13:cny=0.10'"))
    assert review.browse(query()).counts["marginAlert"] == 0
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    fresh = review.browse(query()).groups[0]
    assert fresh.calculationStatus == "ready" and not fresh.marginAlert and not fresh.autoReview.eligible
    assert fresh.quantityMismatch and not fresh.unitMismatch
    assert fresh.contentSha256 == payload["contentSha256"]
    for line in fresh.customsLines:
        assert line.marginStatus == "quantity_mismatch" and line.margin == ""
        assert line.marginNote == "数量不一致（报关行 10，子采购报关合计 9）"
    assert review.browse(query(status="margin_alert")).total == 0
    assert rows(engine, "SELECT id FROM review_records") == []


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


def test_v8_unmatched_prefix_snapshot_rebuilds_without_resync(review, ns, engine):
    declaration = customs("870")
    for _, line in declaration[2]:
        line["custrecord_swc_salesorder_number"] = "销售订单 #SO1"
    save(ns, engine, bundle([purchase()], [declaration]))
    calculations = CalculationService(review)
    calculations.rebuild()
    snapshot = rows(engine, "SELECT id,payload FROM review_declaration_snapshots")[0]
    payload = json.loads(snapshot["payload"])
    for line in payload["customsLines"]:
        line.update(
            margin="",
            marginStatus="unavailable",
            marginNote="对应销售单不唯一，无法计算",
            declaredUnitPriceCny="",
            originalUnitPriceCny="",
        )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_declaration_snapshots SET payload=:p"), {"p": json.dumps(payload)}
        )
        connection.execute(text("UPDATE review_calculation_jobs SET calculation_key='review-v8:cny=0.10'"))
    assert review.browse(query()).groups[0].calculationStatus == "pending"
    calculations.initialize()
    CalculationWorker(calculations).run_once()
    fresh = review.browse(query()).groups[0]
    assert fresh.calculationStatus == "ready" and fresh.contentSha256 == payload["contentSha256"]
    for line in fresh.customsLines:
        assert line.marginStatus == "ok" and line.marginNote == ""
        assert line.originalUnitPriceCny in {"8.894", "1.77"} and line.declaredUnitPriceCny == "10.65"
    assert rows(engine, "SELECT id FROM review_records") == []


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
    # 真实报关单号（夹具为 REAL + CD 编号数字），与 CD 号是不同字段
    real = review.browse(query(declarationNo="不存在，REAL871"))
    assert real.total == 1 and real.groups[0].recordNumber == "CD871"
    assert review.browse(query(declarationNo="REAL870;REAL871")).total == 2
    assert review.browse(query(declarationNo="CD871")).total == 0
    assert review.browse(query(declarationNo="REAL870", recordNo="871")).total == 0
    for field in ("supplierName", "declarantName", "recordNo", "declarationNo", "purchaseOrderNo"):
        assert review.browse(query(**{field: "%"})).total == 0
    assert review.browse(query(recordNo="，；\n ")).total == 2


def test_declarant_filter_uses_header_company_before_counts_and_paging(review, ns, engine, monkeypatch):
    orders, declarations = [], []
    for index, name in enumerate(
        ("上海毅鑫实业有限公司", "上海毅鑫实业有限公司", "上海绎视数码科技有限公司")
    ):
        identity = str(870 + index)
        head = customs(identity)
        for _, line in head[2]:
            line["custrecord_swc_company"] = {"id": "8" if index < 2 else "9", "refName": name}
        orders.append(purchase(str(200 + index), identity))
        declarations.append(head)
    save(ns, engine, bundle(orders, declarations))
    calculations = CalculationService(review)
    calculations.rebuild()
    first = review.browse(query(recordNo="CD870")).groups[0]
    review.approve(int(first.id), ApproveRequest(contentSha256=first.contentSha256), "user:admin")
    CalculationWorker(calculations).run_once()

    def forbidden(*args, **kwargs):
        raise AssertionError("申报抬头筛选应读取已有快照")

    monkeypatch.setattr(review.declarations, "details", forbidden)
    found = review.browse(query(declarantName="上海毅鑫", pageSize=1, page=2))
    assert found.total == found.counts["all"] == found.pages == 2
    assert found.counts["pending"] == found.counts["approved"] == 1
    assert [group.recordNumber for group in found.groups] == ["CD870"]
    assert review.browse(query(declarantName="上海毅鑫", status="approved")).total == 1
    assert review.browse(query(declarantName="上海毅鑫", recordNo="CD872")).total == 0
    # 采购公司和供应商名称不能命中申报抬头字段。
    assert review.browse(query(declarantName="采购公司A")).total == 0
    assert review.browse(query(declarantName="供应商")).total == 0
    assert review.browse(query(declarantName="毅鑫；绎视\n毅鑫")).total == 3
    assert review.browse(query(declarantName="不存在")).total == 0
    assert review.browse(query(declarantName="")).total == 3


def test_bulk_input_limits_and_literal_spaces():
    from backend.core.search_terms import search_terms
    from pydantic import ValidationError

    assert search_terms(" ACME LTD，乙; ACME LTD\n丙 ") == ("ACME LTD", "乙", "丙")
    assert query(recordNo=";".join(str(i) for i in range(50))).recordNo
    assert query(declarantName=" 上海毅鑫，上海绎视 ").declarantName == "上海毅鑫\n上海绎视"
    for value in ("x" * 121, ";".join(str(i) for i in range(51)), "x" * 6501):
        with pytest.raises(ValidationError):
            query(recordNo=value)
        with pytest.raises(ValidationError):
            query(declarantName=value)


def test_creation_date_filter_uses_china_day_boundaries_before_counts_and_paging(review, ns, engine):
    dates = [
        "2026-08-31T15:59:59Z",
        "2026-08-31T16:00:00Z",
        "2026-09-01T15:59:59Z",
        "2026-09-01T16:00:00Z",
        None,
    ]
    for index, created in enumerate(dates):
        identity = str(870 + index)
        head = customs(identity)
        head[1]["created"] = created
        save(ns, engine, bundle([purchase(str(200 + index), identity)], [head]))
    CalculationService(review).rebuild()
    criteria = dict(createdFrom="2026-09-01", createdTo="2026-09-01")
    result = review.browse(query(**criteria, pageSize=1, page=2))
    assert result.total == 2 and result.pages == 2
    assert result.counts["all"] == 2 and result.counts["pending"] == 2
    assert [group.recordNumber for group in result.groups] == ["CD871"]
    assert review.browse(query(**criteria, recordNo="CD872")).total == 1
    assert review.browse(query(createdFrom="2026-10-01", createdTo="2026-10-31")).total == 0
    assert review.browse(query()).total == 5  # 清空日期后包含创建时间缺失的单据。


@pytest.mark.parametrize(
    "values",
    [
        {"createdFrom": "2026-09-01"},
        {"createdTo": "2026-09-01"},
        {"createdFrom": "2026-09-02", "createdTo": "2026-09-01"},
        {"createdFrom": "2026-02-30", "createdTo": "2026-03-01"},
    ],
)
def test_creation_date_filter_validation(values):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        query(**values)


def test_calculation_refreshes_saved_customs_conclusions(review, ns, engine):
    from backend.modules.review.dto.customs_receipt_dto import CustomsImportRequest, CustomsReceiptQuery
    from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
    from backend.tests.test_customs_receipts import row, xlsx

    seed(ns, engine)
    customs_receipts = CustomsReceiptService(engine)
    content = xlsx([row("REAL870", "01", "墨水", "个", 9)])
    customs_receipts.import_file(CustomsImportRequest(filename="回执.xlsx", content=content), "admin")
    # 模拟规则升级前保存的旧结论：计数与筛选读取保存值，与逐行实时比对不一致
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE review_customs_receipts SET match_status = 'matched', quantity_mismatch = 0")
        )
    assert customs_receipts.browse(CustomsReceiptQuery()).counts.matched == 1

    CalculationService(review).rebuild()
    page = customs_receipts.browse(CustomsReceiptQuery())
    assert page.items[0].status == "different"
    assert (page.counts.matched, page.counts.different, page.counts.quantityMismatch) == (0, 1, 1)
