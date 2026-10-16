"""专用 MySQL 验证同请求争用、账套互斥及事件回滚；无配置明确跳过。"""

from dataclasses import replace

import pytest
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.modules.invoice.entity import headers, versions
from backend.modules.invoice.public import InvoicesImported
from backend.modules.sync.dto.lemon_invoice_dto import PullLemonInvoices
from backend.tests.sync.test_lemon_invoices import OWNER, body, count, make_services
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_matching_mysql import race
from sqlalchemy import select


@pytest.fixture
def services(engine, env):
    settings = replace(
        load_settings(env),
        origin="https://invoice.example",
        lemon_app_id="12345",
        lemon_app_secret="secret",
        lemon_redirect_uri="https://invoice.example/api/lemon/oauth/callback",
    )
    return make_services(engine, settings)


def test_concurrent_same_request_only_fetches_once(engine, services):
    accounts, service, upstream, _ = services
    request = PullLemonInvoices(**body())
    assert race(lambda: service.pull(OWNER, request), lambda: service.pull(OWNER, request)) == ["ok", "ok"]
    assert upstream.pulls == 1
    assert count(engine, headers) == count(engine, versions) == 1
    assert accounts.configuration(OWNER)["latest"]["status"] == "completed"


def test_pending_request_blocks_new_runs_and_selection(engine, services):
    accounts, service, upstream, _ = services
    service._start(OWNER, PullLemonInvoices(**body()))
    assert race(
        lambda: service.pull(OWNER, PullLemonInvoices(**body())), lambda: accounts.select(OWNER, "8")
    ) == [409, 409]
    assert upstream.pulls == 0 and count(engine, headers) == 0


def test_event_failure_rolls_back_and_exact_decimal(engine, services):
    accounts, service, upstream, events = services
    upstream.rows[0].update(Amount="99999999999999.99", Tax="0.00", AdValoremTaxTotals="99999999999999.99")
    service.pull(OWNER, PullLemonInvoices(**body()))
    with engine.connect() as connection:
        assert str(connection.scalar(select(headers.c.amount_including_tax))) == "99999999999999.99"

    def fail(connection, event):
        raise ApiError(409, "订阅拒绝")

    events.subscribe(InvoicesImported, fail)
    upstream.rows[0]["IsInvalid"] = 1
    with pytest.raises(ApiError, match="订阅拒绝"):
        service.pull(OWNER, PullLemonInvoices(**body()))
    assert count(engine, versions) == 1
    with engine.connect() as connection:
        assert connection.scalar(select(headers.c.status)) == "normal"
    assert accounts.configuration(OWNER)["latest"]["status"] == "failed"
