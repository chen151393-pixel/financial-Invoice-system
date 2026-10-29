"""低分仍生成建议，商品名称可参与评分，最高分并列不猜配。"""

from backend.modules.matching.dto.matching_dto import QueueQuery
from backend.modules.matching.policy.comparison_policy import purchase_item_match
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import rows


def test_product_name_does_not_get_hidden_by_declaration_name():
    line = {"item_name": "影楼膜闪点", "declaration_name": "冷裱膜"}
    assert purchase_item_match("影楼膜闪点", line) == ("影楼膜闪点", "match")
    assert purchase_item_match("冷裱膜", line) == ("冷裱膜", "match")


def test_name_mismatch_uses_other_evidence_and_stays_pending(engine, world, reviewed):
    lines = [("替代商品甲", *INK[1:]), ("替代商品乙", *FLUID[1:])]
    import_invoices(world, [invoice("26000000000000009701", lines, remark="SUB-200")])
    target = invoice_id(engine, "26000000000000009701")
    found = proposals(world, target)
    assert len(found) == 2
    assert all(next(c for c in row.checks if c.key == "item").result == "mismatch" for row in found)
    assert world["queries"].invoice_queue(QueueQuery()).total == 1
    assert not rows(engine, "SELECT id FROM matching_allocations WHERE status='confirmed'")
    assert not rows(engine, "SELECT id FROM writeback_tasks")
    assert world["proposals"].generate_now([target], "user:admin") == 0


def test_low_confidence_amount_and_unit_difference_is_visible(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000009702", [("其他商品", "箱", "1000", "100000", "0")])])
    target = invoice_id(engine, "26000000000000009702")
    found = proposals(world, target)
    assert len(found) == 2
    assert world["queries"].invoice(target).groups[0].noteReasons
    assert all(row.tier == "low" for row in found)


def test_equal_score_invoice_lines_are_not_arbitrarily_assigned(engine, world, reviewed):
    lines = [("替代甲", *INK[1:]), ("替代乙", *INK[1:])]
    import_invoices(world, [invoice("26000000000000009703", lines, remark="SUB-200")])
    assert proposals(world, invoice_id(engine, "26000000000000009703")) == []
