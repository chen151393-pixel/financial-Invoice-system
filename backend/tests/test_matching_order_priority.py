"""备注单号优先：子单 / 母单范围、供应商差异、完整单号边界与真实导入链路。"""

from decimal import Decimal

import pytest
from backend.modules.matching.dao import allocation_dao
from backend.modules.matching.dto.matching_dto import CandidateQuery, ConfirmBody, QueueQuery
from backend.modules.matching.policy.comparison_policy import order_in_remark
from backend.modules.matching.service.proposal_service import best_candidate
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_task import USER, approve


def context(order, parent, *, supplier="甲公司", unit="个", item="墨水", active=True):
    return {
        "order_no": order,
        "parent_order_no": parent,
        "supplier_name": supplier,
        "supplier_name_normalized": supplier,
        "company_name": "采购公司",
        "company_name_normalized": "采购公司",
        "declaration_name": item,
        "item_name": "普通商品名",
        "unit": unit,
        # 与 source.purchase_lines 一致：单位字典名称，未知编号保留原值
        "unit_name": unit,
        "active": active,
    }


def choose(remark, contexts):
    header = {
        "remark": remark,
        "seller_name": "甲公司",
        "seller_name_normalized": "甲公司",
        "buyer_name": "采购公司",
        "buyer_name_normalized": "采购公司",
    }
    item = {
        "item_name": "*化学品*墨水",
        "unit": "个",
        "quantity": Decimal(10),
        "amount_including_tax": Decimal(100),
    }
    tasks = [
        {
            "purchase_line_id": key,
            "expected_quantity": Decimal(10),
            "received_quantity": Decimal(0),
            "expected_amount": Decimal(100),
            "received_amount": Decimal(0),
        }
        for key in contexts
    ]
    return best_candidate(header, item, tasks, contexts)


@pytest.mark.parametrize("remark", ["对应 SUB-200", "采购单 PO-100"])
def test_order_scope_wins_even_when_other_order_scores_higher(remark):
    contexts = {
        1: context("SUB-300", "PO-999"),
        2: context("SUB-200", "PO-100", supplier="乙公司", unit="箱"),
    }
    winner = choose(remark, contexts)
    outside = choose(remark, {1: contexts[1]})
    assert winner[0]["purchase_line_id"] == 2
    assert winner[2] < outside[2]
    checks = {check["key"]: check for check in winner[3]}
    assert checks["order"]["result"] == "match"
    assert checks["seller"]["result"] == "mismatch"
    assert checks["unit"]["result"] == "mismatch"


def test_parent_scope_compares_product_between_its_children():
    winner = choose(
        "母采购单 PO-100",
        {
            1: context("SUB-300", "PO-999"),
            2: context("SUB-200", "PO-100", item="清洗液"),
            3: context("SUB-201", "PO-100"),
        },
    )
    assert winner[0]["purchase_line_id"] == 3
    assert winner[2] == Decimal(100)


def test_multiple_order_references_form_candidate_scope():
    winner = choose(
        "对应 SUB-200、PO-101",
        {
            1: context("SUB-200", "PO-100", item="清洗液"),
            2: context("SUB-201", "PO-101"),
            3: context("SUB-300", "PO-999"),
        },
    )
    assert winner[0]["purchase_line_id"] == 2


@pytest.mark.parametrize("remark", ["", "采购单 PO-UNKNOWN"])
def test_no_eligible_order_match_falls_back_to_supplier(remark):
    winner = choose(
        remark,
        {
            1: context("SUB-200", "PO-100", supplier="乙公司"),
            2: context("SUB-201", "PO-101"),
        },
    )
    assert winner[0]["purchase_line_id"] == 2
    assert choose(remark, {1: context("SUB-200", "PO-100", supplier="乙公司")}) is None


def test_inactive_order_is_never_selected():
    assert choose("SUB-200", {1: context("SUB-200", "PO-100", active=False)}) is None


@pytest.mark.parametrize(
    ("remark", "number", "matches"),
    [
        ("备注：ＰＯ－１００，尾款", "PO-100", True),
        ("采购sub-200及其他事项", "SUB-200", True),
        ("PO-100/SUB-200", "PO-100", True),
        ("PO-1001", "PO-100", False),
        ("PO-100-2", "PO-100", False),
        ("SUB-PO-100", "PO-100", False),
        ("PO-100_2", "PO-100", False),
        ("", "PO-100", False),
        ("PO-100", None, False),
        ("YE-DQ20260624-Z010；VIG260610-01", "采购订单 #YE-DQ20260624-Z010", True),
        ("PO-100", "Purchase Order #PO-100", True),
        ("PO-100", "采购订单 ＃ＰＯ－１００", True),
        ("PO-1001", "采购订单 #PO-100", False),
        ("PO-100-2", "采购订单 #PO-100", False),
        ("PO-100", "其他说明 #PO-100", False),
        ("任何备注", "采购订单 #", False),
    ],
)
def test_complete_order_number_boundaries(remark, number, matches):
    assert order_in_remark(remark, number) is matches


def test_ns_parent_display_prefix_preserves_order_priority():
    winner = choose(
        "YE-DQ20260624-Z010；VIG260610-01",
        {
            1: context("SUB-300", "PO-999"),
            2: context("YE-DQ20260624-Z010-1", "采购订单 #YE-DQ20260624-Z010", unit="卷"),
        },
    )
    assert winner[0]["purchase_line_id"] == 2
    assert winner[3][0]["result"] == "match"


def late_task(ns, engine, world):
    save(ns, engine, bundle([purchase(), purchase("201", "871")], [customs("870"), customs("871")]))
    approve(world, "CD870")
    number = "26000000000000009193"
    import_invoices(world, [invoice(number, [INK], remark="SUB-201")])
    target = invoice_id(engine, number)
    original = proposals(world, target)[0]
    assert original.purchase.orderNo == "SUB-200"
    approve(world, "CD871")
    return target, original


def test_regenerate_replaces_old_pending_and_repeated_call_is_unchanged(ns, engine, world):
    target, original = late_task(ns, engine, world)
    assert world["proposals"].generate_now([target], USER) == 1
    found = proposals(world, target)
    assert len(found) == 1 and found[0].purchase.orderNo == "SUB-201"
    assert found[0].status == "proposed"
    old = rows(engine, "SELECT * FROM matching_allocations WHERE id=:id", id=int(original.id))[0]
    assert old["status"] == "rejected" and old["reviewed_by"] == USER
    assert "重新生成建议" in old["review_note"]
    assert world["proposals"].generate_now([target], USER) == 0
    assert len(rows(engine, "SELECT id FROM matching_allocations WHERE invoice_id=:id", id=target)) == 2


def test_regenerate_preserves_confirmed_allocation(ns, engine, world):
    target, original = late_task(ns, engine, world)
    world["allocations"].confirm(int(original.id), ConfirmBody(note="测试：人工核实原分配"), USER)
    before = rows(engine, "SELECT * FROM matching_allocations WHERE invoice_id=:id", id=target)
    assert world["proposals"].generate_now([target], USER) == 0
    assert rows(engine, "SELECT * FROM matching_allocations WHERE invoice_id=:id", id=target) == before


def test_regenerate_failure_rolls_back_old_pending_rejection(ns, engine, world, monkeypatch):
    target, original = late_task(ns, engine, world)

    def fail(*args, **kwargs):
        raise RuntimeError("模拟插入失败")

    monkeypatch.setattr(allocation_dao, "insert_allocation", fail)
    with pytest.raises(RuntimeError, match="模拟插入失败"):
        world["proposals"].generate_now([target], USER)
    found = proposals(world, target)
    assert len(found) == 1 and found[0].id == original.id


def test_parent_reference_survives_import_query_and_manual_search(engine, world, reviewed):
    number = "26000000000000009191"
    import_invoices(world, [invoice(number, [INK], seller="另一供应商有限公司", remark="母单 PO-100")])
    target = invoice_id(engine, number)
    found = proposals(world, target)
    assert len(found) == 1
    proposal = found[0]
    checks = {check.key: check for check in proposal.checks}
    assert checks["order"].result == "match"
    assert "母采购单 PO-100" in checks["order"].note
    assert checks["seller"].invoiceValue == "另一供应商有限公司"
    assert checks["seller"].result == "mismatch"
    assert proposal.noteReasons
    assert not world["queries"].invoice_queue(QueueQuery()).rows[0].batch.allowed
    item = world["queries"].invoice(target).items[0]
    result = world["queries"].candidates(
        CandidateQuery(invoiceId=str(target), invoiceItemId=item.id, keyword="PO-100")
    )
    assert result.total == 2
    assert all(
        next(check for check in row.checks if check.key == "order").result == "match" for row in result.rows
    )


def test_manual_candidates_and_proposals_share_order_priority(ns, engine, world):
    target_purchase = purchase("201", "871")
    target_purchase[1]["custrecord_swc_subpo_vendor"] = {"id": "88", "refName": "另一供应商有限公司"}
    for _, line in target_purchase[2]:
        line["custrecord_swc_subpo_item_unit"] = "箱"
    save(ns, engine, bundle([purchase(), target_purchase], [customs("870"), customs("871")]))
    approve(world, "CD870")
    approve(world, "CD871", note="测试单位差异，人工核实来源")
    number = "26000000000000009192"
    import_invoices(world, [invoice(number, [INK], remark="对应 SUB-201")])
    target = invoice_id(engine, number)
    proposal = proposals(world, target)[0]
    assert proposal.purchase.orderNo == "SUB-201"
    item = world["queries"].invoice(target).items[0]
    result = world["queries"].candidates(CandidateQuery(invoiceId=str(target), invoiceItemId=item.id))
    assert result.total == 4
    assert [row.purchase.orderNo for row in result.rows] == ["SUB-201", "SUB-201", "SUB-200", "SUB-200"]
    assert Decimal(result.rows[0].confidence) < Decimal(result.rows[2].confidence)
