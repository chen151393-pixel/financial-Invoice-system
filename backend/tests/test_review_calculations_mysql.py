"""在专用随机 MySQL 库验证后台计算并发；未配置连接时明确跳过。"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from types import SimpleNamespace

import pytest
from backend.core.write_lock import transaction
from backend.modules.review.dao import calculation_job_dao as jobs
from backend.modules.review.service.calculation_service import CalculationService, now_utc
from backend.modules.review.service.calculation_worker import CalculationWorker
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns


def setup_job(engine):
    service = CalculationService(SimpleNamespace(engine=engine, tolerance=Decimal("0.10")))
    with transaction(engine) as connection:
        jobs.request(connection, "test-account", now_utc())
        jobs.set_key(connection, "test-account", service.key, now_utc())
    return service


def test_new_generation_wins_during_background_read(schema_engine, monkeypatch):
    service = setup_job(schema_engine)
    started, resume = Event(), Event()

    def build(account):
        started.set()
        assert resume.wait(10), "并发请求未及时释放计算线程"
        return [], []

    monkeypatch.setattr(service, "build", build)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.calculate, service.pending()[0])
        try:
            assert started.wait(10)
            with transaction(schema_engine) as connection:
                jobs.request(connection, "test-account", now_utc())
        finally:
            resume.set()
        assert future.result(timeout=10) is False
    with schema_engine.connect() as connection:
        queued = jobs.get(connection, "test-account")
    assert queued["requested_revision"] == 2 and queued["completed_revision"] == 0
    assert service.calculate(service.pending()[0]) is True


def test_mysql_only_one_background_consumer(schema_engine, monkeypatch):
    if schema_engine.dialect.name != "mysql":
        pytest.skip("MySQL 命名锁必须在 MySQL 验证")
    service = setup_job(schema_engine)
    started, resume = Event(), Event()
    calls = []

    def build(account):
        calls.append(account)
        started.set()
        assert resume.wait(10)
        return [], []

    monkeypatch.setattr(service, "build", build)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(CalculationWorker(service).run_once)
        try:
            assert started.wait(10)
            CalculationWorker(service).run_once()
            assert calls == ["test-account"]
        finally:
            resume.set()
        future.result(timeout=10)
    assert service.pending() == []


def test_real_database_page_aggregates_are_integer_counts(schema_engine, ns):
    from backend.app import create_events
    from backend.modules.review.dto.review_dto import DeclarationListQuery
    from backend.modules.review.service.review_service import ReviewService
    from backend.modules.source.public import DeclarationService
    from backend.tests.test_source_storage import bundle, customs, purchase, save

    save(ns, schema_engine, bundle([purchase()], [customs("870")]))
    review = ReviewService(schema_engine, DeclarationService(schema_engine), create_events())
    CalculationService(review).rebuild()
    for status in ("all", "pending", "approved", "auto", "margin_alert"):
        page = review.browse(DeclarationListQuery(status=status, pageSize=1))
        assert all(type(count) is int for count in page.counts.values())
        assert type(page.total) is int and type(page.pages) is int
        assert page.total == (1 if status in ("all", "pending", "auto") else 0)
