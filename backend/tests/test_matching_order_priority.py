"""备注单号优先：子单 / 母单范围、供应商模糊召回、整单组合唯一性、完整单号边界与真实导入链路。"""

from decimal import Decimal

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dao import allocation_dao
from backend.modules.matching.dto.matching_dto import CandidateQuery, GroupConfirmBody, QueueQuery
from backend.modules.matching.policy.comparison_policy import order_in_remark, supplier_result
from backend.modules.matching.policy.order_group_policy import choose, plan_groups
from backend.modules.matching.service.group_plan_service import recall_orders
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_task import USER, approve

ORDERS = {"SUB-200": 200, "SUB-201": 201, "SUB-300": 300}


def context(order, parent, *, supplier="甲公司"):
    return {
        "purchase_order_id": ORDERS.get(order, 999),
        "order_no": order,
        "parent_order_no": parent,
        "supplier_name": supplier,
    }


def recall(remark, contexts):
    return recall_orders({"remark": remark, "seller_name": "甲公司"}, dict(enumerate(contexts)))


@pytest.mark.parametrize("remark", ["对应 SUB-200", "采购单 PO-100"])
def test_order_and_supplier_both_recall_candidates(remark):
    found = recall(remark, [context("SUB-300", "PO-999"), context("SUB-200", "PO-100", supplier="乙公司")])
    assert found == [200, 300]


def test_parent_scope_recalls_all_its_children():
    found = recall(
        "母采购单 PO-100",
        [context("SUB-300", "PO-999"), context("SUB-200", "PO-100"), context("SUB-201", "PO-100")],
    )
    assert found == [200, 201, 300]


def test_multiple_order_references_form_candidate_scope():
    found = recall(
        "对应 SUB-200、PO-101",
        [context("SUB-200", "PO-100"), context("SUB-201", "PO-101"), context("SUB-300", "PO-999")],
    )
    assert found == [200, 201, 300]


@pytest.mark.parametrize("remark", ["", "采购单 PO-UNKNOWN"])
def test_no_order_reference_falls_back_to_supplier(remark):
    found = recall(remark, [context("SUB-200", "PO-100", supplier="乙公司"), context("SUB-201", "PO-101")])
    assert found == [201]
    assert recall(remark, [context("SUB-200", "PO-100", supplier="乙公司")]) == []


def test_ns_parent_display_prefix_preserves_order_priority():
    found = recall(
        "YE-DQ20260624-Z010；VIG260610-01",
        [context("SUB-300", "PO-999"), context("SUB-201", "采购订单 #YE-DQ20260624-Z010")],
    )
    assert found == [201, 300]


@pytest.mark.parametrize(
    ("invoice_name", "purchase_name", "result"),
    [
        ("中山帝奇新材料有限公司", "中山帝奇新材料有限公司", "match"),
        ("华盛塑胶制品（深圳）有限公司", "深圳市华盛塑胶制品有限公司", "match"),
        ("广东省东莞市宏达五金有限公司", "东莞宏达五金制品厂", "match"),
        ("宁波华源实业股份有限公司", "宁波华元实业有限公司", "partial"),
        ("甲公司", "乙公司", "mismatch"),
        ("", "乙公司", "missing"),
    ],
)
def test_supplier_fuzzy_rules(invoice_name, purchase_name, result):
    # 去掉括号内容、公司后缀与开头地名后相同或包含为一致，相近为部分一致
    assert supplier_result(invoice_name, purchase_name) == result


def amounts(**values):
    return {key: (Decimal(quantity), Decimal(amount)) for key, (quantity, amount) in values.items()}


def test_choose_requires_exact_unique_combination():
    targets = {1: (Decimal(30), Decimal(300))}
    contributions = {
        10: {1: (Decimal(10), Decimal(100))},
        11: {1: (Decimal(20), Decimal(200))},
        12: {1: (Decimal(5), Decimal(55))},
    }
    assert choose(targets, contributions) == [11, 10]
    # 另一张同样金额的单可以替换其中一张：组合不唯一，不自动建议
    assert choose(targets, contributions | {13: {1: (Decimal(20), Decimal(200))}}) is None
    assert choose({1: (Decimal(31), Decimal(300))}, contributions) is None


def test_plan_covers_whole_invoice_first_then_each_line():
    items = [
        {"id": 1, "quantity": Decimal(10), "amount_including_tax": Decimal(100)},
        {"id": 2, "quantity": Decimal(5), "amount_including_tax": Decimal(50)},
    ]
    # 一张子采购单同时含两种商品：整票一组
    assert plan_groups(items, [7], {7: {1: (Decimal(10), Decimal(100)), 2: (Decimal(5), Decimal(50))}}) == [
        ([7], [1, 2])
    ]
    # 两张单各对一行；第二行没有合适的单时只建议第一行
    contributions = {8: {1: (Decimal(10), Decimal(100))}, 9: {2: (Decimal(4), Decimal(40))}}
    assert plan_groups(items, [8, 9], contributions) == [([8], [1])]


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


def group_of(world, target):
    (found,) = world["queries"].invoice(target).groups
    return found


def late_task(ns, engine, world):
    save(ns, engine, bundle([purchase(), purchase("201", "871")], [customs("870"), customs("871")]))
    approve(world, "CD870")
    number = "26000000000000009193"
    import_invoices(world, [invoice(number, [INK, FLUID], remark="SUB-201")])
    target = invoice_id(engine, number)
    # SUB-201 尚未审核、没有开票任务：备注单号无法定位，按供应商召回 SUB-200 整单
    original = group_of(world, target)
    assert [order.orderNo for order in original.orders] == ["SUB-200"]
    approve(world, "CD871")
    return target, original


def test_regenerate_replaces_old_pending_and_repeated_call_is_unchanged(ns, engine, world):
    target, original = late_task(ns, engine, world)
    assert world["proposals"].generate_now([target], USER) == 2
    found = group_of(world, target)
    assert [order.orderNo for order in found.orders] == ["SUB-201"]
    old = rows(engine, "SELECT * FROM matching_allocations WHERE id=:id", id=int(original.allocationIds[0]))[
        0
    ]
    assert old["status"] == "rejected" and old["reviewed_by"] == USER
    assert "重新生成建议" in old["review_note"]
    assert world["proposals"].generate_now([target], USER) == 0
    assert len(rows(engine, "SELECT id FROM matching_allocations WHERE invoice_id=:id", id=target)) == 4


def test_regenerate_preserves_confirmed_allocation(ns, engine, world):
    target, original = late_task(ns, engine, world)
    body = GroupConfirmBody(invoiceId=str(target), note="测试：人工核实原分配")
    world["allocations"].confirm_group(original.id, body, USER)
    before = rows(engine, "SELECT * FROM matching_allocations WHERE invoice_id=:id", id=target)
    assert world["proposals"].generate_now([target], USER) == 0
    assert rows(engine, "SELECT * FROM matching_allocations WHERE invoice_id=:id", id=target) == before
    # 已整组通过后再次提交同一组为重放，不重复记账
    world["allocations"].confirm_group(original.id, body, USER)
    with pytest.raises(ApiError, match="不存在"):
        world["allocations"].confirm_group("00000000-0000-4000-8000-000000000000", body, USER)


def test_regenerate_failure_rolls_back_old_pending_rejection(ns, engine, world, monkeypatch):
    target, original = late_task(ns, engine, world)

    def fail(*args, **kwargs):
        raise RuntimeError("模拟插入失败")

    monkeypatch.setattr(allocation_dao, "insert_allocation", fail)
    with pytest.raises(RuntimeError, match="模拟插入失败"):
        world["proposals"].generate_now([target], USER)
    assert group_of(world, target).id == original.id


def test_parent_reference_survives_import_query_and_manual_search(engine, world, reviewed):
    number = "26000000000000009191"
    import_invoices(world, [invoice(number, [INK, FLUID], seller="华盛贸易有限公司", remark="母单 PO-100")])
    target = invoice_id(engine, number)
    found = group_of(world, target)
    checks = {check.key: check for check in found.items[0].checks}
    assert checks["order"].result == "match"
    assert "母采购单 PO-100" in checks["order"].purchaseValue
    assert checks["seller"].invoiceValue == "华盛贸易有限公司"
    assert checks["seller"].result == "mismatch"
    assert found.noteReasons
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
    save(ns, engine, bundle([purchase(), target_purchase], [customs("870"), customs("871")]))
    approve(world, "CD870")
    approve(world, "CD871")
    number = "26000000000000009192"
    import_invoices(world, [invoice(number, [INK, FLUID], remark="对应 SUB-201")])
    target = invoice_id(engine, number)
    # 两张订单均召回，SUB-201 的综合得分最高。
    assert [order.orderNo for order in group_of(world, target).orders] == ["SUB-201"]
    item = world["queries"].invoice(target).items[0]
    result = world["queries"].candidates(CandidateQuery(invoiceId=str(target), invoiceItemId=item.id))
    assert result.total == 4
    assert [row.purchase.orderNo for row in result.rows] == ["SUB-201", "SUB-200", "SUB-201", "SUB-200"]
    assert [Decimal(row.confidence) for row in result.rows] == sorted(
        (Decimal(row.confidence) for row in result.rows), reverse=True
    )
