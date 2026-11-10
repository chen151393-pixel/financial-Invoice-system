"""单位与实际幅度异常独立分类；兼容旧快照，在 SQL 中按整单去重、筛选和分页。"""

import json

from backend.app import create_events
from backend.modules.review.dto.review_dto import DeclarationListQuery
from backend.modules.review.service.calculation_service import CalculationService
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService
from backend.tests.review_helpers import comparable_purchase as purchase
from backend.tests.review_helpers import customs_prices as customs
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, save
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import text


def test_unit_filter_counts_whole_declarations_before_pagination(schema_engine, ns):
    engine = schema_engine
    for i in range(6):
        save(ns, engine, bundle([purchase(str(200 + i), str(870 + i))], [customs(str(870 + i))]))
    review = ReviewService(engine, DeclarationService(engine), create_events())
    CalculationService(review).rebuild()
    statuses = [
        ["unit_mismatch", "unit_mismatch"],
        ["unit_mismatch", "negative"],
        ["quantity_mismatch"],
        ["negative"],
        ["unit_mismatch"],  # 已审核的不进入待核对分类。
        ["ok"],
    ]
    with engine.begin() as connection:
        snapshots = (
            connection.execute(
                text("SELECT id,payload FROM review_declaration_snapshots ORDER BY customs_declaration_id")
            )
            .mappings()
            .all()
        )
        for i, snapshot in enumerate(snapshots):
            payload = json.loads(snapshot["payload"])
            line = payload["customsLines"][0]
            payload["customsLines"] = [{**line, "marginStatus": status} for status in statuses[i]]
            # 原因文案、子采购备注不能造成误命中。
            payload["customsLines"][0]["marginNote"] = "unit_mismatch"
            payload["customsLines"][0]["purchaseLines"][0]["note"] = "unit_mismatch"
            payload["marginAlert"] = i != 5
            # 模拟升级前的快照：没有独立标记，marginAlert 混入单位和数量异常。
            payload.pop("unitMismatch", None)
            payload.pop("quantityMismatch", None)
            payload["review"]["status"] = "approved" if i == 4 else "pending"
            connection.execute(
                text(
                    "UPDATE review_declaration_snapshots SET payload=:payload, margin_alert=:alert, "
                    "review_status=:status WHERE id=:id"
                ),
                {
                    "id": snapshot["id"],
                    "payload": json.dumps(payload),
                    "alert": i != 5,
                    "status": payload["review"]["status"],
                },
            )
    page = review.browse(DeclarationListQuery(status="unit_mismatch", pageSize=1))
    assert page.counts["marginAlert"] == 2
    assert page.counts["unitMismatch"] == page.total == 2
    assert page.pages == 2 and [g.recordNumber for g in page.groups] == ["CD871"]
    assert page.groups[0].unitMismatch and page.groups[0].marginAlert
    second = review.browse(DeclarationListQuery(status="unit_mismatch", pageSize=1, page=2))
    assert [g.recordNumber for g in second.groups] == ["CD870"]
    assert second.groups[0].unitMismatch and not second.groups[0].marginAlert
    filtered = review.browse(DeclarationListQuery(status="unit_mismatch", recordNo="CD870"))
    assert filtered.total == filtered.counts["unitMismatch"] == 1
    assert filtered.counts["marginAlert"] == 0
    assert review.browse(DeclarationListQuery(status="unit_mismatch", recordNo="CD873")).total == 0
    price = review.browse(DeclarationListQuery(status="margin_alert"))
    assert price.total == 2
    assert [g.recordNumber for g in price.groups] == ["CD873", "CD871"]
    assert all(g.marginAlert for g in price.groups)
    assert not price.groups[0].unitMismatch
    quantity = review.browse(DeclarationListQuery(recordNo="CD872"))
    assert quantity.groups[0].quantityMismatch
    assert not quantity.groups[0].marginAlert and not quantity.groups[0].unitMismatch
    assert quantity.counts["marginAlert"] == quantity.counts["unitMismatch"] == 0
    with engine.begin() as connection:
        connection.execute(text("UPDATE review_calculation_jobs SET requested_revision=requested_revision+1"))
    dirty = review.browse(DeclarationListQuery(status="unit_mismatch"))
    assert dirty.total == dirty.counts["unitMismatch"] == dirty.counts["marginAlert"] == 0
    stale = review.browse(DeclarationListQuery())
    assert all(not (g.marginAlert or g.unitMismatch or g.quantityMismatch) for g in stale.groups)
