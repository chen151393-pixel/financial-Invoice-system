"""先有发票后生成任务：真实事件链自动建议、整单组合、幂等和审核事务回滚。"""

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dao import allocation_dao
from backend.modules.matching.dto.matching_dto import GroupConfirmBody
from backend.modules.matching.service import task_proposal_service
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, group, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_task import USER, approve
from sqlalchemy import text


def existing(world, engine, number="26000000000000008701", lines=None, **kwargs):
    import_invoices(world, [invoice(number, lines or [INK, FLUID], remark="SUB-200", **kwargs)])
    return invoice_id(engine, number)


def test_task_creation_generates_existing_invoice_proposal(ns, engine, world):
    target = existing(world, engine)
    assert not proposals(world, target)
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")
    found = group(world, target)
    assert len(found.allocationIds) == 2 and found.confirm.allowed
    assert {row.status for row in proposals(world, target)} == {"proposed"}
    assert all(row["received_amount"] == 0 for row in rows(engine, "SELECT received_amount FROM task_lines"))
    assert world["proposals"].generate_now([target], USER) == 0


def test_short_invoice_suggests_difference_without_confirming(ns, engine, world):
    target = existing(world, engine, lines=[("墨水", "个", "4", "35.58", "4.62")])
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")
    found = group(world, target)
    check = next(check for check in found.items[0].checks if check.key == "quantity")
    assert check.differenceLabel == "发票少 16"
    with pytest.raises(ApiError, match="请填写审核说明"):
        world["allocations"].confirm_group(found.id, GroupConfirmBody(invoiceId=str(target)), USER)


def test_reapproval_refreshes_basis_and_does_not_duplicate(ns, engine, world):
    target = existing(world, engine)
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")
    old_ids = group(world, target).allocationIds
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    approve(world, "CD870", "金额更正")
    found = group(world, target)
    assert set(found.allocationIds).isdisjoint(old_ids)
    with engine.connect() as connection:
        saved = allocation_dao.by_invoices(connection, [target])
    assert all(row["status"] == "rejected" for row in saved if str(row["id"]) in old_ids)
    assert len(proposals(world, target)) == 2
    assert world["proposals"].generate_now([target], USER) == 0


def test_new_task_can_complete_multi_order_combination(ns, engine, world):
    target = existing(world, engine, lines=[("墨水", "个", "40", "241.00", "0")])
    orders = [purchase("200", "870"), purchase("201", "871")]
    declarations = [customs("870"), customs("871")]
    for order in orders:
        order[2][1][1]["custrecord_swc_subpo_item_bgname"] = "墨水"
    for declaration in declarations:
        declaration[2][1][1]["custrecord_swc_delare_name"] = "墨水"
    save(ns, engine, bundle(orders, declarations))
    approve(world, "CD870", "合并品名")
    first = group(world, target)
    assert len(first.orders) == 1
    approve(world, "CD871", "合并品名")
    found = group(world, target)
    assert {row.orderNo for row in found.orders} == {"SUB-200", "SUB-201"}
    assert all(
        check.result == "match" for check in found.items[0].checks if check.key in ("quantity", "amount")
    )


def test_confirmed_invoice_is_not_changed_by_new_task(ns, engine, world):
    target = existing(world, engine)
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")
    world["allocations"].confirm_group(group(world, target).id, GroupConfirmBody(invoiceId=str(target)), USER)
    with engine.connect() as connection:
        before = allocation_dao.by_invoices(connection, [target])
    save(ns, engine, bundle([purchase(), purchase("201", "871")], [customs("870"), customs("871")]))
    approve(world, "CD871")
    with engine.connect() as connection:
        assert allocation_dao.by_invoices(connection, [target]) == before


def test_generation_failure_rolls_back_review_and_tasks(ns, engine, world, monkeypatch):
    target = existing(world, engine)
    save(ns, engine, bundle([purchase()], [customs("870")]))

    def fail(*args, **kwargs):
        raise ApiError(409, "模拟建议保存失败")

    monkeypatch.setattr(task_proposal_service, "generate", fail)
    with pytest.raises(ApiError, match="建议保存失败"):
        approve(world, "CD870")
    assert not rows(engine, "SELECT id FROM task_tasks")
    assert not proposals(world, target)
    monkeypatch.undo()
    approve(world, "CD870")
    assert len(proposals(world, target)) == 2


def test_pagination_reaches_older_invoices_and_skips_incomplete(ns, engine, world, monkeypatch):
    older = existing(world, engine)
    newer = existing(world, engine, "26000000000000008702")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE invoice_headers SET detail_status = 'incomplete' WHERE id = :id"), {"id": newer}
        )
    from backend.modules.invoice.service import invoice_reader

    monkeypatch.setattr(invoice_reader, "STATUS_SCOPE_BATCH", 1)
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")
    assert len(proposals(world, older)) == 2 and not proposals(world, newer)
