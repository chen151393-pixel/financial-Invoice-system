"""隔离 MySQL：统计期间发生确认时保持同一快照，结束后恢复连接默认隔离级别。"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from backend.modules.matching.dto.matching_dto import ConfirmBody
from backend.modules.matching.service import invoice_totals_service
from backend.tests.test_invoice_totals import amount, prepare, totals
from backend.tests.test_invoice_totals import (
    test_all_pages_and_header_only_invoices as test_all_pages_and_header_only_invoices,
)
from backend.tests.test_invoice_totals import (
    test_version_review_history_and_cancellation as test_version_review_history_and_cancellation,
)
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_task import USER


def test_concurrent_confirmation_does_not_mix_snapshot(engine, world, reviewed, monkeypatch):
    first, _ = prepare(engine, world)
    read_scope = invoice_totals_service.read_invoice_amount_scope
    fired = False

    def confirm_after_header_read(connection, filters, **kwargs):
        nonlocal fired
        result = read_scope(connection, filters, **kwargs)
        if not fired:
            fired = True
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(world["allocations"].confirm, int(first.id), ConfirmBody(), USER).result(
                    timeout=15
                )
        return result

    monkeypatch.setattr(invoice_totals_service, "read_invoice_amount_scope", confirm_after_header_read)
    assert amount(totals(world)[0], "pendingAmount") == Decimal("120.50")
    assert amount(totals(world)[0], "pendingAmount") == Decimal("20")
    with engine.connect() as connection:
        assert connection.get_isolation_level() == "READ COMMITTED"
