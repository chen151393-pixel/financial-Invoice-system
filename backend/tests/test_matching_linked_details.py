"""已关联详情沿用审核快照；隔离 SQLite，不改变确认记录或调用 NS。"""

import json
from decimal import Decimal

import pytest
from backend.modules.matching.dto.matching_dto import CancelBody, GroupConfirmBody
from backend.modules.matching.entity import allocations
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_matching_manual_order import SHORT, body, candidates, target
from backend.tests.test_source_storage import rows
from backend.tests.test_task import USER
from sqlalchemy import update


def link_short(world, engine):
    invoice_id, item_id = target(world, engine, "26000000000000009971", SHORT)
    order = candidates(world, invoice_id, item_id).rows[0]
    world["allocations"].create_manual_order(
        body(invoice_id, item_id, order, note="核实少开金额，差额结束"), USER
    )
    return invoice_id


def test_linked_whole_order_retains_comparison_and_original_order_amount(engine, world, reviewed):
    invoice_id = link_short(world, engine)
    before = rows(engine, "SELECT * FROM matching_allocations ORDER BY id")
    value = world["queries"].invoice(invoice_id)
    assert not value.groups and len(value.linkedGroups) == 1
    group = value.linkedGroups[0]
    assert group.confidence is None and group.tier == "manual"
    assert not group.confirm.allowed and not group.reject.allowed
    part = group.items[0]
    assert part.quantity == "20" and Decimal(part.amount) == Decimal("120.50")
    assert {line.purchaseLineId for line in part.lines} == {
        row.purchaseLineId for row in value.items[0].allocations if row.status == "confirmed"
    }
    amount = next(check for check in part.checks if check.key == "amount")
    assert Decimal(amount.purchaseValue) == Decimal("120.50")
    assert Decimal(amount.invoiceValue) == Decimal("40.20")
    assert amount.result == "mismatch"
    assert value.items[0].confirmedAmount == "40.2"
    assert rows(engine, "SELECT * FROM matching_allocations ORDER BY id") == before


def test_confirmed_suggestion_keeps_multi_line_comparisons(engine, world, reviewed):
    number = "26000000000000009972"
    import_invoices(world, [invoice(number, [INK, FLUID], remark="SUB-200")])
    found = invoice_id(engine, number)
    pending = world["queries"].invoice(found)
    group = pending.groups[0]
    world["allocations"].confirm_group(
        group.id, GroupConfirmBody(invoiceId=str(found), note="已核实整单"), USER
    )
    confirmed = world["queries"].invoice(found)
    assert not confirmed.groups and len(confirmed.linkedGroups) == 1
    linked = confirmed.linkedGroups[0]
    assert {part.invoiceItemId for part in linked.items} == {item.id for item in confirmed.items}
    assert {part.invoiceItemId: part.checks for part in linked.items} == {
        part.invoiceItemId: part.checks for part in group.items
    }
    assert linked.allocationIds == group.allocationIds


@pytest.mark.parametrize("change", ["cancelled", "needs_review", "legacy"])
def test_incomplete_or_legacy_group_falls_back_to_individual_details(engine, world, reviewed, change):
    found = link_short(world, engine)
    value = world["queries"].invoice(found)
    linked = [row for row in value.items[0].allocations if row.status == "confirmed"]
    if change == "cancelled":
        world["allocations"].cancel(int(linked[0].id), CancelBody(reason="核对后取消一条关联"), USER)
    else:
        with engine.begin() as connection:
            if change == "needs_review":
                values = {"verification_status": "needs_review"}
            else:
                stored = rows(
                    engine, "SELECT checks FROM matching_allocations WHERE id = :id", id=int(linked[0].id)
                )[0]["checks"]
                checks = json.loads(stored) if isinstance(stored, str) else stored
                checks.pop("orderShare")
                values = {"checks": checks}
            connection.execute(
                update(allocations).where(allocations.c.id == int(linked[0].id)).values(**values)
            )
    current = world["queries"].invoice(found)
    assert not current.linkedGroups
    assert any(row.status == "confirmed" and row.checks for row in current.items[0].allocations)
