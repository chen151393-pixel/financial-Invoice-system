"""隔离 MySQL 中验证补拉请求并发，不操作正式发票。"""

from uuid import uuid4

from backend.modules.invoice.entity import headers, items, versions
from backend.modules.sync.dto.lemon_detail_dto import RefreshLemonDetails
from backend.modules.sync.service.lemon_detail_refresh_service import LemonDetailRefreshService
from backend.tests.sync.test_lemon_detail_matching import flow as flow
from backend.tests.sync.test_lemon_detail_matching import pull
from backend.tests.sync.test_lemon_invoices import OWNER, count
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import world as world
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_matching_mysql import race
from sqlalchemy import select


def test_concurrent_selected_refresh_keeps_one_version(engine, flow):
    pull(flow)
    with engine.connect() as connection:
        identifier = str(connection.scalar(select(headers.c.id)))
    service = LemonDetailRefreshService(flow[1])
    body = RefreshLemonDetails(invoiceIds=[identifier], requestId=str(uuid4()))
    results = race(lambda: service.refresh(OWNER, body), lambda: service.refresh(OWNER, body))
    assert results == ["ok", "ok"]
    assert count(engine, headers) == count(engine, versions) == 1
    assert count(engine, items) == 2


def test_concurrent_different_refresh_requests_serialize(engine, flow):
    pull(flow)
    with engine.connect() as connection:
        identifier = str(connection.scalar(select(headers.c.id)))
    service = LemonDetailRefreshService(flow[1])

    def refresh():
        return service.refresh(OWNER, RefreshLemonDetails(invoiceIds=[identifier], requestId=str(uuid4())))

    results = race(refresh, refresh)
    assert results in (["ok", "ok"], [409, "ok"])
    assert count(engine, versions) == 1 and count(engine, items) == 2
