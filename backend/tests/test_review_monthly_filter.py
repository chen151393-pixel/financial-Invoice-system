"""本月财务审核筛选：北京时间边界、分页、搜索及全部月份入口。"""

from datetime import UTC, datetime

import pytest
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.service import review_query_service
from backend.modules.review.service.calculation_service import CalculationService
from backend.modules.review.service.review_query_service import month_bounds_utc
from backend.tests.review_helpers import comparable_purchase as purchase
from backend.tests.review_helpers import customs_prices as customs
from backend.tests.test_review_calculations import review as review
from backend.tests.test_source_storage import bundle, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import text


@pytest.mark.parametrize(
    "moment,start,end",
    [
        ("2026-11-26T12:00:00+00:00", "2026-10-31T16:00:00", "2026-11-30T16:00:00"),
        ("2026-12-31T16:00:00+00:00", "2026-12-31T16:00:00", "2027-01-31T16:00:00"),
        ("2024-02-29T12:00:00+00:00", "2024-01-31T16:00:00", "2024-02-29T16:00:00"),
    ],
)
def test_month_bounds_follow_beijing_calendar(moment, start, end):
    assert month_bounds_utc(datetime.fromisoformat(moment)) == (
        datetime.fromisoformat(start),
        datetime.fromisoformat(end),
    )


def test_monthly_filter_uses_same_counts_before_paging_and_keeps_search(review, ns, engine, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 11, 26, 8, tzinfo=UTC)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(review_query_service, "datetime", FrozenDateTime)
    for index in range(6):
        identity = str(870 + index)
        save(ns, engine, bundle([purchase(str(200 + index), identity)], [customs(identity)]))
    CalculationService(review).rebuild()
    for item in review.browse(DeclarationListQuery()).groups:
        if item.recordNumber != "CD875":
            review.approve(int(item.id), ApproveRequest(contentSha256=item.contentSha256), "user:admin")
    stamps = (
        "2026-10-31T15:59:59.999999",  # 北京时间上月最后一刻
        "2026-10-31T16:00:00",  # 本月起点，包含
        "2026-11-17T08:00:00",
        "2026-11-30T15:59:59.999999",  # 本月最后一刻，包含
        "2026-11-30T16:00:00",  # 下月起点，不包含
    )
    with engine.begin() as connection:
        for index, stamp in enumerate(stamps):
            connection.execute(
                text(
                    "UPDATE review_records SET approved_at=:stamp WHERE customs_declaration_id="
                    "(SELECT id FROM source_customs_declarations WHERE record_no=:number)"
                ),
                {"stamp": datetime.fromisoformat(stamp), "number": f"CD{870 + index}"},
            )
    CalculationService(review).rebuild()
    first = review.browse(DeclarationListQuery(status="approved_this_month", pageSize=2))
    second = review.browse(DeclarationListQuery(status="approved_this_month", pageSize=2, page=2))
    assert first.total == second.total == first.counts["approvedThisMonth"] == 3
    assert first.counts["approved"] == 5 and first.counts["pending"] == 1
    assert first.pages == second.pages == 2
    assert {item.recordNumber for item in first.groups + second.groups} == {"CD871", "CD872", "CD873"}
    assert len(first.groups) == 2 and len(second.groups) == 1
    assert review.browse(DeclarationListQuery(status="approved_this_month", pageSize=2, page=3)).groups == []
    narrowed = review.browse(DeclarationListQuery(status="approved_this_month", recordNo="CD872"))
    assert narrowed.total == narrowed.counts["approvedThisMonth"] == 1
    assert narrowed.groups[0].recordNumber == "CD872"
    previous = review.browse(DeclarationListQuery(status="approved_this_month", recordNo="CD870"))
    assert previous.total == previous.counts["approvedThisMonth"] == 0 and previous.groups == []
    assert review.browse(DeclarationListQuery(status="approved")).total == 5
