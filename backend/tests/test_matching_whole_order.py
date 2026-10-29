"""整单候选、汇总票拆分、原子确认、过期及重复请求；使用隔离 SQLite 数据。"""

from decimal import Decimal
from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dto.order_matching_dto import OrderCandidateQuery, OrderConfirmBody
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_task import USER, approve
from sqlalchemy import text


def candidate(world, target, **kwargs):
    return world["queries"].order_candidates(OrderCandidateQuery(invoiceId=str(target), **kwargs)).rows[0]


def confirmation(target, found, **kwargs):
    return OrderConfirmBody(
        requestId=uuid4(),
        invoiceId=str(target),
        purchaseOrderId=found.purchaseOrderId,
        fingerprint=found.fingerprint,
        note="已核对整单票面与采购明细",
        **kwargs,
    )


@pytest.fixture
def aggregate(ns, engine, world):
    order = purchase()
    order[2][1][1]["custrecord_swc_subpo_item_bgname"] = "墨水"
    declaration = customs("870")
    declaration[2][1][1]["custrecord_swc_delare_name"] = "墨水"
    save(ns, engine, bundle([order], [declaration]))
    approve(world, "CD870", "同品名按整单核实")
    import_invoices(
        world, [invoice("26000000000000009901", [("墨水", "个", "20", "120.50", "0")], remark="PO-100")]
    )
    return invoice_id(engine, "26000000000000009901")


def test_aggregate_preview_and_atomic_confirmation(engine, world, aggregate):
    found = candidate(world, aggregate)
    assert found.lineCount == 2 and found.remainingAmount == "120.5"
    assert found.confirm.allowed and found.orderMatched
    assert len(found.allocations) == 2
    assert sum(Decimal(row.invoiceQuantity) for row in found.allocations) == Decimal(20)
    assert sum(Decimal(row.amount) for row in found.allocations) == Decimal("120.50")
    assert len(proposals(world, aggregate)) == 2
    assert world["proposals"].generate_now([aggregate], USER) == 0
    body = confirmation(aggregate, found)
    view = world["allocations"].confirm_order(body, USER)
    assert len(view.items) == 1 and view.items[0].quantity == "20"
    confirmed = [row for row in view.items[0].allocations if row.status == "confirmed"]
    assert len(confirmed) == 2
    assert {row["status"] for row in rows(engine, "SELECT status FROM task_lines")} == {"received"}
    repeated = world["allocations"].confirm_order(body, USER)
    assert repeated == view
    with pytest.raises(ApiError, match="不能复用"):
        world["allocations"].confirm_order(body.model_copy(update={"note": "变更证据"}), USER)
    assert not world["queries"].order_candidates(OrderCandidateQuery(invoiceId=str(aggregate))).rows


def test_second_line_failure_rolls_back_proposals_and_progress(engine, world, aggregate, monkeypatch):
    before = rows(engine, "SELECT id, status FROM matching_allocations ORDER BY id")
    original = world["allocations"]._manual
    called = 0

    def failing(connection, body, actor):
        nonlocal called
        called += 1
        if called == 2:
            raise ApiError(409, "模拟第二行失败")
        return original(connection, body, actor)

    monkeypatch.setattr(world["allocations"], "_manual", failing)
    with pytest.raises(ApiError, match="第二行失败"):
        world["allocations"].confirm_order(confirmation(aggregate, candidate(world, aggregate)), USER)
    assert rows(engine, "SELECT id, status FROM matching_allocations ORDER BY id") == before
    assert all(row["received_amount"] == 0 for row in rows(engine, "SELECT received_amount FROM task_lines"))


def test_stale_progress_and_missing_task_block_whole_order(engine, world, aggregate):
    found = candidate(world, aggregate)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE task_lines SET received_amount = 1 WHERE id = (SELECT x.id FROM (SELECT MIN(id) AS id FROM task_lines) x)"
            )
        )
    with pytest.raises(ApiError, match="已变化"):
        world["allocations"].confirm_order(confirmation(aggregate, found), USER)
    assert not candidate(world, aggregate).confirm.allowed
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE task_lines SET status = 'superseded' WHERE id = (SELECT x.id FROM (SELECT MIN(id) AS id FROM task_lines) x)"
            )
        )
    found = candidate(world, aggregate)
    assert found.lineCount == 2 and not found.confirm.allowed
    assert "任务行" in found.confirm.reason


def test_multi_item_invoice_matches_whole_order(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000009902", [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000009902")
    found = candidate(world, target)
    assert found.confirm.allowed and len(found.allocations) == 2
    view = world["allocations"].confirm_order(confirmation(target, found), USER)
    assert all(item.confirmedQuantity == "10" for item in view.items)


def test_unit_evidence_required_and_converted_quantity_conserved(engine, world, aggregate):
    with engine.begin() as connection:
        connection.execute(text("UPDATE invoice_items SET unit = '箱', quantity = 10"))
    query = {"conversionNumerator": Decimal(2), "conversionDenominator": Decimal(1)}
    found = candidate(world, aggregate, **query)
    assert found.confirm.allowed
    assert sum(Decimal(part.invoiceQuantity) for part in found.allocations) == 10
    body = confirmation(aggregate, found, **query)
    with pytest.raises(ApiError, match="证据"):
        world["allocations"].confirm_order(body, USER)
    view = world["allocations"].confirm_order(
        body.model_copy(update={"conversionEvidence": "包装证据：每箱 2 个"}), USER
    )
    assert view.items[0].confirmedQuantity == "10"
    assert all(
        row["received_quantity"] == 10 for row in rows(engine, "SELECT received_quantity FROM task_lines")
    )
