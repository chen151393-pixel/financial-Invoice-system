"""一张子采购单只由一张发票开具（2026-11-10）：整单通过后，其他发票上占用同一子采购单的待审核建议自动失效。"""

from sqlalchemy import text

from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, confirm_group, group, import_invoices, invoice_id
from backend.tests.test_matching import engine as engine  # 共用夹具
from backend.tests.test_matching import ns as ns  # 共用夹具
from backend.tests.test_matching import reviewed as reviewed  # 共用夹具
from backend.tests.test_matching import world as world  # 共用夹具
from backend.tests.test_source_storage import rows
from backend.tests.test_task import USER

FIRST, SECOND = "26000000000000009401", "26000000000000009402"


def allocations(engine, number_id):
    return rows(engine, "SELECT * FROM matching_allocations WHERE invoice_id=:id ORDER BY id", id=number_id)


def two_invoices(engine, world):
    # 两张票都按备注命中 SUB-200，在任何一张通过前都会生成该单的待审核建议
    import_invoices(world, [invoice(FIRST, [INK, FLUID], remark="SUB-200")], "first.xlsx")
    import_invoices(world, [invoice(SECOND, [INK, FLUID], remark="SUB-200")], "second.xlsx")
    first, second = invoice_id(engine, FIRST), invoice_id(engine, SECOND)
    assert group(world, first) and group(world, second)
    return first, second


def test_confirming_one_invoice_retires_other_proposals_on_same_order(engine, world, reviewed):
    first, second = two_invoices(engine, world)
    confirm_group(world, first)
    retired = allocations(engine, second)
    assert retired and all(row["status"] == "rejected" for row in retired)
    assert all(row["reviewed_by"] == "system" and FIRST in row["review_note"] for row in retired)
    assert world["queries"].invoice(second).groups == []
    # 已通过的分配不受影响
    assert all(row["status"] == "confirmed" for row in allocations(engine, first))


def test_regenerate_clears_leftover_proposal_on_taken_order(engine, world, reviewed):
    first, second = two_invoices(engine, world)
    confirm_group(world, first)
    # 模拟部署前遗留：另一张票的旧建议仍为待审核
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE matching_allocations SET status='proposed', reviewed_by=NULL, "
                "reviewed_at=NULL, review_note=NULL WHERE invoice_id=:id"
            ),
            {"id": second},
        )
    assert world["queries"].invoice(second).groups
    assert world["proposals"].generate_now([second], USER) == 0
    assert all(
        row["status"] == "rejected" and FIRST in row["review_note"] for row in allocations(engine, second)
    )
    assert world["queries"].invoice(second).groups == []
