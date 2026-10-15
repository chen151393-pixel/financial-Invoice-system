"""MySQL 并发：同一发票行的容量不被并发分配超用；同一任务行的已收合计不丢失更新。

只在提供 BUSINESS_MIGRATION_TEST_SERVER_URL 时运行：随机新建 MySQL 库、执行迁移、测试后删除。
SQLite 为单连接，不能代替本测试声称并发正确。
"""

import os
import threading
from uuid import uuid4

import pytest
from backend.core.database import make_business_engine
from backend.core.errors import ApiError
from backend.manage import upgrade_schema
from backend.modules.matching.dto.matching_dto import ConfirmBody, ManualBody, RejectBody
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals, task
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
