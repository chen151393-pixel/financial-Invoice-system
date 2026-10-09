"""整票置信度、保存关联与分配完成度的列表展示规则。"""

from decimal import Decimal

from backend.modules.matching.service import MatchingService
from backend.modules.matching.summary import matching_summary
from backend.tests.test_matching_allocations import sample


def test_high_confidence_requires_unique_full_invoice_coverage():
    invoice, heads, lines = sample()
    lines[0].update(declaration_quantity=Decimal("6"), amount=Decimal("60"))
    service = MatchingService(None, None)
    assert service.evaluate(invoice, heads, lines, [])["summary"]["confidence"] == "高"
    # 两行争用同一条采购明细不能成为整票高可信。
    invoice["lines"].append({**invoice["lines"][0], "id": "12"})
    assert service.evaluate(invoice, heads, lines, [])["summary"]["confidence"] == "待核实"
    invoice["lines"][1]["item"] = "另一商品"
    assert service.evaluate(invoice, heads, lines, [])["summary"]["confidence"] == "有差异"
    invoice["lines"].pop()
    heads[0]["supplier_name"] = "名称不同"
    assert service.evaluate(invoice, heads, lines, [])["summary"]["confidence"] == "有差异"


def test_conflicting_clues_and_multiple_candidates_are_not_high_confidence():
    invoice, heads, lines = sample()
    lines[0].update(declaration_quantity=Decimal("6"), amount=Decimal("60"))
    service = MatchingService(None, None)
    conflict = service.evaluate(invoice, heads, lines, [], customs_no="CD999")
    assert conflict["summary"]["confidence"] != "高"
    lines.append({**lines[0], "id": 22})
    assert service.evaluate(invoice, heads, lines, [])["summary"]["validation"] == "多个候选，待确认"


def test_unmatched_and_allocation_statuses():
    invoice, _heads, _lines = sample()
    assert matching_summary(invoice, [], [], [])["validation"] == "待匹配"
    allocation = {"invoiceLineId": "11", "quantity": "2", "needsReview": False}
    partial = matching_summary(invoice, [], [], [allocation])
    assert partial["method"] == "数量分配" and partial["validation"] == "部分分配"
    complete = matching_summary(invoice, [], [], [allocation, {**allocation, "quantity": "4"}])
    assert complete["validation"] == "已确认"
    assert matching_summary(invoice, [], [], [{**allocation, "needsReview": True}])["confidence"] == "待复核"
    normal_link = {"needsReview": False, "warnings": []}
    assert matching_summary(invoice, [], [normal_link], [])["confidence"] == "一致"
