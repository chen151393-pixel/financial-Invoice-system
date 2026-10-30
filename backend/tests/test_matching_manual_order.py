"""手动整单关联：一张子采购单只由一张发票开具，后端生成记账数，发票少按差异结束；使用隔离 SQLite 数据。"""

from decimal import Decimal
from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dto.manual_order_dto import ManualOrderBody
from backend.modules.matching.dto.matching_dto import CandidateQuery, GroupConfirmBody, GroupRejectBody
from backend.modules.matching.policy.order_group_policy import ONE_INVOICE
from backend.modules.matching.service import manual_order_service
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import group, import_invoices, invoice_id
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_matching_whole_order import aggregate as aggregate
from backend.tests.test_source_storage import rows
from backend.tests.test_task import USER
from backend.tests.test_unit_display import dictionary as dictionary

# 子采购单 SUB-200：墨水 10 个 100.50 元、清洗液 10 个 20.00 元，整单 20 个 120.50 元
SHORT = ("墨水", "个", "4", "35.58", "4.62")  # 含税 40.20，发票少
OVER = ("墨水", "个", "25", "132.74", "17.26")  # 含税 150.00，发票多


def target(world, engine, number, line, remark="SUB-200", *, keep_proposal=False):
    """导入发票；整单有差异时系统也会生成待审核建议，人工关联前先驳回。"""
    import_invoices(world, [invoice(number, [line], remark=remark)])
    found = invoice_id(engine, number)
    if not keep_proposal:
        for proposal in world["queries"].invoice(found).groups:
            world["allocations"].reject_group(proposal.id, GroupRejectBody(invoiceId=str(found)), USER)
    return found, world["queries"].invoice(found).items[0].id


def candidates(world, invoice, item, keyword=""):
    query = CandidateQuery(invoiceId=str(invoice), invoiceItemId=item, keyword=keyword)
    return world["queries"].manual_order_candidates(query)


def body(invoice, item, order, **kwargs):
    return ManualOrderBody(
        requestId=uuid4(),
        invoiceId=str(invoice),
        invoiceItemId=item,
        purchaseOrderId=order.purchaseOrderId,
        **kwargs,
    )


def task_lines(engine):
    return rows(
        engine,
        "SELECT received_quantity, received_amount, status, closed_with_difference FROM task_lines ORDER BY id",
    )


def test_candidates_are_whole_orders_with_lines(engine, world, reviewed):
    invoice, item = target(world, engine, "26000000000000009911", SHORT)
    result = candidates(world, invoice, item)
    assert result.total == 1
    order = result.rows[0]
    assert order.orderNo == "SUB-200" and order.orderMatched and not order.block
    assert len(order.lines) == 2 and {line.orderNo for line in order.lines} == {"SUB-200"}
    assert order.remainingQuantity == "20" and order.remainingAmount == "120.5"
    quantity = next(check for check in order.checks if check.key == "quantity")
    assert quantity.result == "mismatch" and quantity.differenceLabel == "发票少 16"
    assert candidates(world, invoice, item, "SUB-200").rows == result.rows
    assert not candidates(world, invoice, item, "不存在的单号").rows


def test_default_shows_only_best_and_keyword_needs_three_characters(engine, world, reviewed, monkeypatch):
    invoice, item = target(world, engine, "26000000000000009915", SHORT)
    default = candidates(world, invoice, item)
    assert len(default.rows) == 1 and default.rows[0].confidence != "0"
    with pytest.raises(ApiError, match="至少输入 3 个字符"):
        candidates(world, invoice, item, " S2 ")
    # 与发票行没有任何相符项（置信度 0）的子采购单不作默认展示，仍可按单号查到
    monkeypatch.setattr(manual_order_service, "compare_group", lambda *args: ([], Decimal(0)))
    unrelated = candidates(world, invoice, item)
    assert not unrelated.rows and unrelated.total == 1
    assert [row.orderNo for row in candidates(world, invoice, item, "SUB-200").rows] == ["SUB-200"]


def test_short_invoice_closes_whole_order_by_difference(engine, world, reviewed):
    invoice, item = target(world, engine, "26000000000000009912", SHORT)
    order = candidates(world, invoice, item).rows[0]
    with pytest.raises(ApiError, match="差额按差异结束") as error:
        world["allocations"].create_manual_order(body(invoice, item, order), USER)
    assert error.value.status == 400
    request = body(invoice, item, order, note="供应商只开墨水 4 个，其余不再开票")
    view = world["allocations"].create_manual_order(request, USER)
    confirmed = [row for row in view.items[0].allocations if row.status == "confirmed"]
    # 记账数由后端按明细顺序记到发票为止：墨水 4 个 40.20 元，清洗液 0
    assert sorted((row.quantity, row.amount) for row in confirmed) == [("0", "0"), ("4", "40.2")]
    assert all(row.tier == "manual" for row in confirmed)
    lines = task_lines(engine)
    assert [row["status"] for row in lines] == ["received", "received"]
    assert all(row["closed_with_difference"] for row in lines)
    events = rows(engine, "SELECT reason FROM task_events WHERE event_type = 'difference_closed'")
    assert [row["reason"] for row in events] == ["供应商只开墨水 4 个，其余不再开票"] * 2
    # 同一操作重复提交只生效一次；请求编号不能用于不同内容
    assert world["allocations"].create_manual_order(request, USER) == view
    with pytest.raises(ApiError, match="不能复用"):
        world["allocations"].create_manual_order(request.model_copy(update={"note": "改了说明"}), USER)
    assert len(rows(engine, "SELECT id FROM task_events WHERE event_type = 'difference_closed'")) == 2


def test_order_invoiced_once_cannot_be_linked_to_another_invoice(engine, world, reviewed):
    invoice, item = target(world, engine, "26000000000000009913", SHORT)
    order = candidates(world, invoice, item).rows[0]
    world["allocations"].create_manual_order(body(invoice, item, order, note="只开墨水"), USER)
    other, other_item = target(world, engine, "26000000000000009916", SHORT)
    # 已开完（含按差异结束）的子采购单不再出现在候选里；直接提交也被拒绝
    assert candidates(world, other, other_item, "SUB-200").rows == []
    with pytest.raises(ApiError, match="只能由一张发票开具") as error:
        world["allocations"].create_manual_order(body(other, other_item, order, note="再开一次"), USER)
    assert error.value.message == ONE_INVOICE


def test_over_invoice_records_full_order_and_needs_note(engine, world, reviewed):
    invoice, item = target(world, engine, "26000000000000009914", OVER)
    order = candidates(world, invoice, item).rows[0]
    before = rows(engine, "SELECT id, status FROM matching_allocations ORDER BY id")
    with pytest.raises(ApiError, match="请填写审核说明"):
        world["allocations"].create_manual_order(body(invoice, item, order), USER)
    assert rows(engine, "SELECT id, status FROM matching_allocations ORDER BY id") == before
    view = world["allocations"].create_manual_order(
        body(invoice, item, order, note="供应商多开 5 个，按合同补开"), USER
    )
    assert view.items[0].confirmedQuantity == "20" and view.items[0].confirmedAmount == "120.5"
    lines = task_lines(engine)
    assert [row["status"] for row in lines] == ["received", "received"]
    assert not any(row["closed_with_difference"] for row in lines)
    assert not rows(engine, "SELECT id FROM task_events WHERE event_type = 'difference_closed'")


def test_short_invoice_auto_proposal_closes_by_difference_on_confirm(engine, world, reviewed):
    invoice, _ = target(world, engine, "26000000000000009917", SHORT, keep_proposal=True)
    proposal = group(world, invoice)
    assert "发票少于子采购单，差额按差异结束" in proposal.noteReasons
    quantity = next(check for check in proposal.items[0].checks if check.key == "quantity")
    assert (quantity.purchaseValue, quantity.differenceLabel) == ("20", "发票少 16")
    with pytest.raises(ApiError, match="请填写审核说明"):
        world["allocations"].confirm_group(proposal.id, GroupConfirmBody(invoiceId=str(invoice)), USER)
    world["allocations"].confirm_group(
        proposal.id, GroupConfirmBody(invoiceId=str(invoice), note="只开墨水 4 个"), USER
    )
    assert all(row["closed_with_difference"] for row in task_lines(engine))


def test_pending_suggestion_blocks_manual_order(engine, world, aggregate):
    item = world["queries"].invoice(aggregate).items[0].id
    order = candidates(world, aggregate, item).rows[0]
    with pytest.raises(ApiError, match="请先驳回"):
        world["allocations"].create_manual_order(body(aggregate, item, order), USER)
