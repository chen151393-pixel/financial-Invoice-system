"""批量详情与分页在随机专用 MySQL 库中复用同一组行为和查询次数断言。"""

from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_supplier_tasks import grouped as grouped
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task_query_performance import (
    test_bulk_detail_keeps_unknown_delivery_guard_for_successor as test_bulk_detail_keeps_unknown_delivery_guard_for_successor,
)
from backend.tests.test_task_query_performance import (
    test_detail_query_count_does_not_grow_with_members as test_detail_query_count_does_not_grow_with_members,
)
from backend.tests.test_task_query_performance import (
    test_pagination_only_loads_current_page_and_keeps_global_counts as test_pagination_only_loads_current_page_and_keeps_global_counts,
)
from backend.tests.test_task_query_performance import (
    test_supplier_pagination_keeps_completed_scope_separate as test_supplier_pagination_keeps_completed_scope_separate,
)
