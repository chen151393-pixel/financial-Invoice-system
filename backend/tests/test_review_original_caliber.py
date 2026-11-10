"""报关行原始口径对报关口径（2026-11-09）：单位不一致、数量不一致不计算申报幅度，需人工核对。"""

from decimal import Decimal

import pytest
from backend.modules.review.dto.review_dto import DeclarationListQuery
from backend.modules.review.policy.auto_review_policy import auto_review_reasons, margin_alert
from backend.modules.review.policy.margin_policy import caliber_mismatch, declared_margin
from backend.tests.test_review import events as events  # 共用夹具
from backend.tests.test_review import group
from backend.tests.test_review import service as service  # 共用夹具
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具


def row(**changes):
    return {
        "unit": "盒",
        "quantity": Decimal("10332"),
        "declared_unit": "平方米",
        "declared_quantity": Decimal("17687.33"),
        **changes,
    }


@pytest.mark.parametrize(
    ("changes", "status", "note"),
    [
        # 截图 CD000968 热转印膜：原始 10332 盒，报关 17687.33 平方米
        ({}, "unit_mismatch", "原始单位“盒”与报关单位“平方米”不一致，不计算申报幅度"),
        (
            {"unit": "平方米", "quantity": Decimal("17000")},
            "quantity_mismatch",
            "原始数量 17000 与报关数量 17687.33 不一致，不计算申报幅度",
        ),
        ({"unit": " 平方米 ", "quantity": Decimal("17687.330")}, None, None),
        # 任一口径缺少单位或数量时不比这一项，交给原有申报幅度规则
        ({"unit": None}, None, None),
        ({"unit": "平方米", "quantity": None}, None, None),
    ],
)
def test_caliber_mismatch(changes, status, note):
    found = caliber_mismatch(row(**changes))
    assert (found["status"], found["note"]) == (status, note) if status else found is None


def test_unit_code_is_resolved_before_comparing():
    assert caliber_mismatch(row(unit="12", declared_unit="平方米"), {"12": "平方米"}) is not None
    assert caliber_mismatch(row(unit="12", quantity=Decimal("17687.33")), {"12": "平方米"}) is None


def test_mismatch_skips_margin_and_needs_manual_review():
    margin = declared_margin(row(), [], {}, {})
    assert (margin["status"], margin["margin"]) == ("unit_mismatch", None)
    assert not margin_alert([margin])
    reasons = auto_review_reasons("pending", False, 0, [{"amount": Decimal(1)}], True, [margin])
    assert reasons == ["报关行原始口径与报关口径不一致：" + margin["note"]]


def test_review_page_shows_original_price_and_mismatch(ns, engine, service):
    save(ns, engine, bundle([purchase()], [customs("870", original=(Decimal("5"), "千克"))]))
    result = group(service, "CD870")
    line = result.customsLines[0]
    assert (line.originalQuantity, line.originalPriceUnit, line.originalPrice) == ("5", "千克", "3")
    assert (line.quantity, line.unit) == ("10", "个")
    assert line.marginStatus == "unit_mismatch" and line.margin == ""
    assert result.unitMismatch and not result.marginAlert and not result.autoReview.eligible
    filtered = service.browse(DeclarationListQuery(status="unit_mismatch"))
    assert filtered.counts["unitMismatch"] == filtered.total == 1
    assert [item.recordNumber for item in filtered.groups] == ["CD870"]
    assert service.browse(DeclarationListQuery(status="margin_alert")).total == 0
