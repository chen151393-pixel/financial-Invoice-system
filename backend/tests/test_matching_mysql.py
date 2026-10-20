"""MySQL 并发：同一发票行的容量不被并发分配超用；同一任务行的已收合计不丢失更新。

只在提供 BUSINESS_MIGRATION_TEST_SERVER_URL 时运行：随机新建 MySQL 库、执行迁移、测试后删除。
SQLite 为单连接，不能代替本测试声称并发正确。
"""

import os
import threading
from decimal import Decimal
from uuid import uuid4

import pytest
from backend.core.database import make_business_engine
from backend.core.errors import ApiError
from backend.manage import upgrade_schema
from backend.modules.matching.dto.matching_dto import ConfirmBody, ManualBody, RejectBody
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals, task
from backend.tests.test_matching import (
    test_queue_counts_with_all_confidence_tiers as test_queue_counts_with_all_confidence_tiers,
)
from backend.tests.test_matching import world as world  # 共用夹具
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from backend.tests.test_task import USER, approve
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def engine():
    server_url = os.environ.get("BUSINESS_MIGRATION_TEST_SERVER_URL")
    if not server_url:
        pytest.skip("未提供专用MySQL建库连接，未执行发票比对并发测试")
    url = make_url(server_url)
    if url.drivername != "mysql+pymysql":
        pytest.fail("并发测试必须使用MySQL")
    database = "codex_" + uuid4().hex + "_matching_test"
    server = create_engine(url.set(database=None))
    engine, created = None, False
    try:
        with server.connect() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
            )
            created = True
        target = url.set(database=database).render_as_string(hide_password=False)
        upgrade_schema(target)
        engine = make_business_engine(target)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with server.connect() as connection:
                connection.execute(text(f"DROP DATABASE `{database}`"))
        server.dispose()


def race(*actions):
    barrier, results = threading.Barrier(len(actions)), []

    def run(action):
        barrier.wait()
        try:
            action()
            results.append("ok")
        except ApiError as error:
            results.append(error.status)

    threads = [threading.Thread(target=run, args=(action,)) for action in actions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return sorted(results, key=str)


@pytest.fixture
def reviewed(ns, engine, world):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")


def test_concurrent_allocations_cannot_exceed_invoice_item(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000007001", [INK])])  # 无备注：仍按销售方召回一条建议
    target = invoice_id(engine, "26000000000000007001")
    item_id = world["queries"].invoice(target).items[0].id
    for proposal in proposals(world, target):
        world["allocations"].reject(int(proposal.id), RejectBody(), USER)
    lines = [row["id"] for row in rows(engine, "SELECT id FROM source_purchase_order_lines ORDER BY id")]

    def allocate(line_id):
        body = ManualBody(
            requestId=uuid4(),
            invoiceId=str(target),
            invoiceItemId=item_id,
            purchaseLineId=str(line_id),
            quantity="10",
            amount="100.50",
            note="并发测试",
        )
        return lambda: world["allocations"].create_manual(body, USER)

    assert race(allocate(lines[0]), allocate(lines[1])) == [409, "ok"]
    assert len(rows(engine, "SELECT id FROM matching_allocations WHERE status = 'confirmed'")) == 1


def test_concurrent_confirms_on_same_purchase_line_keep_totals(engine, world, reviewed):
    half = ("墨水", "个", "5", "44.47", "5.78")  # 含税 50.25，两张合计等于应开 100.50
    import_invoices(world, [invoice("26000000000000007002", [half, FLUID], remark="SUB-200")], "a.xlsx")
    import_invoices(world, [invoice("26000000000000007003", [half], remark="SUB-200")], "b.xlsx")
    first = next(
        p for p in proposals(world, invoice_id(engine, "26000000000000007002")) if p.amount == "50.25"
    )
    second = proposals(world, invoice_id(engine, "26000000000000007003"))[0]
    note = ConfirmBody(note="分两张票开具")
    results = race(
        lambda: world["allocations"].confirm(int(first.id), note, USER),
        lambda: world["allocations"].confirm(int(second.id), note, USER),
    )
    assert results == ["ok", "ok"]
    line = rows(engine, "SELECT * FROM task_lines ORDER BY purchase_line_id")[0]
    assert str(line["received_amount"]).rstrip("0").rstrip(".") == "100.5" and line["status"] == "received"
    assert task(engine)["status"] == "partially_received"


def test_concurrent_reapproval_only_one_successor(ns, engine, world, reviewed):
    save(ns, engine, bundle([purchase(amounts=("120.50", "20.00"))], [customs("870")]))
    assert race(lambda: approve(world, "CD870"), lambda: approve(world, "CD870")) == ["ok", "ok"]
    assert len(rows(engine, "SELECT id FROM task_tasks WHERE status<>'superseded'")) == 1
    assert len(rows(engine, "SELECT id FROM review_purchase_bases WHERE status='active'")) == 2
    assert len(rows(engine, "SELECT id FROM task_lines WHERE status<>'superseded'")) == 2


def test_source_refresh_racing_confirmation_never_leaves_stale_valid_receipt(ns, engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000007004", [INK], remark="SUB-200")])
    proposal = proposals(world, invoice_id(engine, "26000000000000007004"))[0]
    results = race(
        lambda: save(ns, engine, bundle([purchase(amounts=("120.50", "20.00"))], [customs("870")])),
        lambda: world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER),
    )
    assert results in (["ok", "ok"], [409, "ok"])
    first = rows(engine, "SELECT * FROM task_lines ORDER BY purchase_line_id")[0]
    assert first["requires_review"] and first["received_amount"] == 0
    assert not rows(
        engine, "SELECT id FROM matching_allocations WHERE status='confirmed' AND verification_status='valid'"
    )


def test_cancel_racing_invoice_refresh_has_no_lost_progress(engine, world, reviewed):
    from backend.modules.matching.dto.matching_dto import CancelBody

    number = "26000000000000007005"
    import_invoices(world, [invoice(number, [INK], remark="SUB-200")])
    proposal = proposals(world, invoice_id(engine, number))[0]
    world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)
    assert race(
        lambda: world["allocations"].cancel(int(proposal.id), CancelBody(reason="撤回"), USER),
        lambda: import_invoices(world, [invoice(number, [INK], remark="SUB-200 changed")]),
    ) == ["ok", "ok"]
    first = rows(engine, "SELECT * FROM task_lines ORDER BY purchase_line_id")[0]
    assert first["received_amount"] == 0 and first["pending_amount"] == 0
    assert (
        rows(engine, "SELECT status FROM matching_allocations WHERE id=:id", id=int(proposal.id))[0]["status"]
        == "cancelled"
    )


def test_reapproval_racing_cancel_and_invoice_refresh(ns, engine, world, reviewed):
    from backend.modules.matching.dto.matching_dto import CancelBody
    from backend.tests.test_ledger_versions import confirm_all

    _, found = confirm_all(engine, world)
    save(ns, engine, bundle([purchase(amounts=("120.50", "20.00"))], [customs("870")]))
    assert race(
        lambda: approve(world, "CD870"),
        lambda: world["allocations"].cancel(int(found[0].id), CancelBody(reason="并发撤回"), USER),
        lambda: import_invoices(
            world, [invoice("26000000000000008801", [INK, FLUID], remark="SUB-200 修订")]
        ),
    ) == ["ok", "ok", "ok"]
    active = rows(engine, "SELECT * FROM task_lines WHERE status<>'superseded' ORDER BY purchase_line_id")
    assert len(active) == 2 and active[0]["expected_amount"] == Decimal("120.50")
    assert active[0]["received_amount"] == 0 and active[0]["pending_amount"] == 0
    assert active[1]["received_amount"] == 0 and active[1]["pending_amount"] == 20
    assert len(rows(engine, "SELECT id FROM task_tasks WHERE status<>'superseded'")) == 1


def test_mysql_subscriber_failure_rolls_back_version_and_receipts(engine, world, reviewed, monkeypatch):
    from backend.modules.task.service import progress_service
    from backend.tests.test_ledger_versions import confirm_all
    from sqlalchemy.exc import SQLAlchemyError

    confirm_all(engine, world)

    def fail(*args):
        raise SQLAlchemyError("isolated MySQL subscriber failure")

    monkeypatch.setattr(progress_service, "apply_receipt", fail)
    with pytest.raises(ApiError):
        import_invoices(world, [invoice("26000000000000008801", [INK, FLUID], remark="SUB-200 修订")])
    assert len(rows(engine, "SELECT id FROM invoice_versions")) == 1
    assert task(engine)["status"] == "completed"
    assert all(
        r["verification_status"] == "valid" for r in rows(engine, "SELECT * FROM matching_allocations")
    )
