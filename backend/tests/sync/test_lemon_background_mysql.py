"""专用 MySQL：同请求、同时间触发、多个消费者的竞争。"""

from dataclasses import replace
from datetime import datetime
from threading import Event, Thread

import pytest
from backend.core.config import load_settings
from backend.modules.invoice.entity import headers
from backend.modules.sync.dao import lemon_plan_dao
from backend.modules.sync.service.lemon_worker import LemonWorker
from backend.tests.sync.test_lemon_background import background_services, drain, plan, request
from backend.tests.sync.test_lemon_invoices import OWNER, count
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_matching_mysql import race


@pytest.fixture
def world(engine, env):
    settings = replace(
        load_settings(env),
        origin="https://invoice.example",
        lemon_app_id="12345",
        lemon_app_secret="secret",
        lemon_redirect_uri="https://invoice.example/api/lemon/oauth/callback",
    )
    return background_services(engine, settings)


def test_concurrent_submit_and_scheduler_are_idempotent(world):
    body = request()
    assert race(lambda: world.batches.submit(OWNER, body), lambda: world.batches.submit(OWNER, body)) == [
        "ok",
        "ok",
    ]
    assert world.batches.list(OWNER)["total"] == 1
    world.plans.save(OWNER, plan())
    now = datetime(2026, 10, 20)
    with world.engine.begin() as connection:
        lemon_plan_dao.save(connection, world.worker.scope, {"next_run_at": now})
    assert race(lambda: world.plans.tick(OWNER, now), lambda: world.plans.tick(OWNER, now)) == ["ok", "ok"]
    assert world.batches.list(OWNER)["total"] == 2


def test_worker_lock_and_manual_same_account_exclusion(world):
    from backend.core.errors import ApiError
    from backend.modules.sync.dto.lemon_invoice_dto import PullLemonInvoices
    from backend.tests.sync.test_lemon_invoices import body as manual_body

    body = request(accountMode="selected", accountIds=["7"])
    world.batches.submit(OWNER, body)
    world.worker.run_once()
    entered, release = Event(), Event()
    original = world.upstream.invoices

    def read(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    world.upstream.invoices = read
    first = Thread(target=world.worker.run_once)
    first.start()
    try:
        assert entered.wait(10)
        LemonWorker(world.plans, world.jobs).run_once()
        assert world.upstream.pulls == 0
        with pytest.raises(ApiError, match="待核实"):
            world.invoices.pull(OWNER, PullLemonInvoices(**manual_body()))
    finally:
        release.set()
        first.join(15)
    assert not first.is_alive()
    assert world.upstream.pulls == 1 and count(world.engine, headers) == 1
    assert world.batches.read(OWNER, body.requestId)["phase"] == "completed"


def test_mysql_events_and_second_run_do_not_duplicate_invoices(world):
    body = request()
    world.batches.submit(OWNER, body)
    assert drain(world, body.requestId)["created"] == 2
    second = request()
    world.batches.submit(OWNER, second)
    assert drain(world, second.requestId)["created"] == 0
    assert count(world.engine, headers) == 2
