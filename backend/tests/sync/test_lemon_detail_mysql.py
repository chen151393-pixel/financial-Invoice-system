"""在随机隔离 MySQL 库验证补明细账本、事件回滚和重复拉取竞争。"""

from backend.modules.invoice.entity import headers, items, versions
from backend.tests.sync.test_lemon_detail_matching import (
    flow as flow,
)
from backend.tests.sync.test_lemon_detail_matching import (
    pull,
)
from backend.tests.sync.test_lemon_detail_matching import (
    test_detail_failure_and_subscriber_failure_preserve_previous_ledger as test_detail_failure_and_subscriber_failure_preserve_previous_ledger,
)
from backend.tests.sync.test_lemon_detail_matching import (
    test_reordering_no_new_version_changed_quantity_reopens_review as test_reordering_no_new_version_changed_quantity_reopens_review,
)
from backend.tests.sync.test_lemon_invoices import count
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_matching_mysql import race


def test_concurrent_new_requests_do_not_duplicate_items_or_versions(engine, reviewed, flow):
    results = race(lambda: pull(flow), lambda: pull(flow))
    assert results in (["ok", "ok"], [409, "ok"])
    assert count(engine, headers) == count(engine, versions) == 1
    assert count(engine, items) == 2
