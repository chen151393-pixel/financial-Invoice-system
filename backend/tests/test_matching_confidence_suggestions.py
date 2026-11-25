"""低分仍生成建议（无单号时须数量或金额一致），商品名称可参与评分，最高分并列不猜配。"""

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
    # 备注命中单号时，数量、金额、单位都不一致也保留为低分建议，差异交人工核实
    lines = [("其他商品", "箱", "1000", "100000", "0")]
    import_invoices(world, [invoice("26000000000000009702", lines, remark="SUB-200")])
    target = invoice_id(engine, "26000000000000009702")
    found = proposals(world, target)
    assert len(found) == 2
    assert world["queries"].invoice(target).groups[0].noteReasons
    assert all(row.tier == "low" for row in found)


def test_supplier_guess_without_quantity_or_amount_is_not_suggested(engine, world, reviewed):
    # 备注无单号，只有供应商相同，数量和金额都对不上：不把同供应商的开放子采购单猜成建议
    import_invoices(world, [invoice("26000000000000009704", [("其他商品", "箱", "1000", "100000", "0")])])
    assert proposals(world, invoice_id(engine, "26000000000000009704")) == []


def test_supplier_guess_with_matching_amount_is_still_suggested(engine, world, reviewed):
    # 备注无单号，墨水数量对不上但含税金额一致：有硬指标，照常生成待审建议，差异交人工核实
    lines = [("墨水", "个", "12", "88.94", "11.56"), FLUID]
    import_invoices(world, [invoice("26000000000000009705", lines)])
    found = proposals(world, invoice_id(engine, "26000000000000009705"))
    assert len(found) == 2
    ink = next(
        row for row in found if next(c for c in row.checks if c.key == "quantity").result == "mismatch"
    )
    assert next(c for c in ink.checks if c.key == "amount").result == "match"


def test_equal_score_invoice_lines_are_not_arbitrarily_assigned(engine, world, reviewed):
    lines = [("替代甲", *INK[1:]), ("替代乙", *INK[1:])]
    import_invoices(world, [invoice("26000000000000009703", lines, remark="SUB-200")])
    assert proposals(world, invoice_id(engine, "26000000000000009703")) == []
