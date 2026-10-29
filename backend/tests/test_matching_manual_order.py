"""手动整单关联：候选按整张子采购单、逐条明细可改小（部分开票）、整组保存并通过；使用隔离 SQLite 数据。"""

from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dto.manual_order_dto import ManualOrderBody
from backend.modules.matching.dto.matching_dto import CandidateQuery
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import import_invoices, invoice_id
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_matching_whole_order import aggregate as aggregate
from backend.tests.test_source_storage import rows
from backend.tests.test_task import USER
from backend.tests.test_unit_display import dictionary as dictionary


def target(world, engine, number, line, remark="SUB-200"):
    import_invoices(world, [invoice(number, [line], remark=remark)])
    found = invoice_id(engine, number)
    return found, world["queries"].invoice(found).items[0].id


def candidates(world, invoice, item, keyword=""):
    query = CandidateQuery(invoiceId=str(invoice), invoiceItemId=item, keyword=keyword)
    return world["queries"].manual_order_candidates(query)


def body(invoice, item, order, shares, **kwargs):
    return ManualOrderBody(
        requestId=uuid4(),
        invoiceId=str(invoice),
        invoiceItemId=item,
        purchaseOrderId=order.purchaseOrderId,
        lines=[
            {"purchaseLineId": line.purchaseLineId, "quantity": quantity, "amount": amount}
            for line, (quantity, amount) in zip(order.lines, shares)
        ],
        **kwargs,
    )


def test_candidates_are_whole_orders_with_lines(engine, world, reviewed):
    invoice, item = target(world, engine, "26000000000000009911", ("墨水", "个", "4", "35.58", "4.62"))
    result = candidates(world, invoice, item)
    assert result.total == 1
    order = result.rows[0]
    assert order.orderNo == "SUB-200" and order.orderMatched and not order.block
    assert len(order.lines) == 2 and {line.orderNo for line in order.lines} == {"SUB-200"}
    assert order.remainingQuantity == "20" and order.remainingAmount == "120.5"
    assert any(check.key == "quantity" for check in order.checks)
    assert not candidates(world, invoice, item, "不存在的单号").rows


def test_partial_invoice_saves_whole_order_group(engine, world, reviewed):
    invoice, item = target(world, engine, "26000000000000009912", ("墨水", "个", "4", "35.58", "4.62"))
    order = candidates(world, invoice, item).rows[0]
    request = body(invoice, item, order, [("4", "40.20"), ("0", "0")], note="部分开票，本票只开墨水 4 个")
    view = world["allocations"].create_manual_order(request, USER)
    confirmed = [row for row in view.items[0].allocations if row.status == "confirmed"]
    assert len(confirmed) == 1 and confirmed[0].quantity == "4" and confirmed[0].amount == "40.2"
    assert confirmed[0].tier == "manual" and confirmed[0].checks
    received = rows(engine, "SELECT received_quantity, received_amount FROM task_lines ORDER BY id")
    assert sorted(row["received_amount"] for row in received) == [0, pytest.approx(40.2)]
    # 同一操作重复提交只生效一次；请求编号不能用于不同内容
    assert world["allocations"].create_manual_order(request, USER) == view
    with pytest.raises(ApiError, match="不能复用"):
        world["allocations"].create_manual_order(request.model_copy(update={"note": "改了说明"}), USER)


def test_must_cover_every_open_line_of_the_order(engine, world, reviewed):
    invoice, item = target(world, engine, "26000000000000009913", ("墨水", "个", "4", "35.58", "4.62"))
    order = candidates(world, invoice, item).rows[0]
    partial = body(invoice, item, order, [("4", "40.20")])
    with pytest.raises(ApiError, match="可分配明细不一致"):
        world["allocations"].create_manual_order(partial, USER)


def test_invoice_capacity_and_overrun_note_roll_back(engine, world, reviewed):
    invoice, item = target(world, engine, "26000000000000009914", ("墨水", "个", "12", "106.19", "13.81"))
    order = candidates(world, invoice, item).rows[0]
    before = rows(engine, "SELECT id, status FROM matching_allocations ORDER BY id")
    with pytest.raises(ApiError, match="超过发票行"):
        world["allocations"].create_manual_order(
            body(invoice, item, order, [("10", "100.50"), ("10", "20.00")], note="核对"), USER
        )
    with pytest.raises(ApiError, match="超出剩余应开"):
        world["allocations"].create_manual_order(
            body(invoice, item, order, [("12", "120.00"), ("0", "0")]), USER
        )
    assert rows(engine, "SELECT id, status FROM matching_allocations ORDER BY id") == before
    view = world["allocations"].create_manual_order(
        body(invoice, item, order, [("12", "120.00"), ("0", "0")], note="供应商多发 2 个，按合同补开"), USER
    )
    assert view.items[0].confirmedQuantity == "12"
    assert rows(engine, "SELECT exceeds_expected FROM matching_allocations WHERE status = 'confirmed'")[0][
        "exceeds_expected"
    ]


def test_pending_suggestion_blocks_manual_order(engine, world, aggregate):
    item = world["queries"].invoice(aggregate).items[0].id
    order = candidates(world, aggregate, item).rows[0]
    with pytest.raises(ApiError, match="请先驳回"):
        world["allocations"].create_manual_order(
            body(
                aggregate,
                item,
                order,
                [(line.remainingQuantity, line.remainingAmount) for line in order.lines],
            ),
            USER,
        )
