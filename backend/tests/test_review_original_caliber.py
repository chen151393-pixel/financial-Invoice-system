"""原始报关口径变化时，幅度仍按实际采购单位与报关单位校验。"""

from decimal import Decimal

import pytest
from backend.modules.review.dto.review_dto import DeclarationListQuery
from backend.modules.review.policy.auto_review_policy import auto_review_reasons, margin_alert
from backend.modules.review.policy.margin_policy import declared_margin
from backend.tests.review_helpers import comparable_purchase as purchase
from backend.tests.test_review import events as events  # 共用夹具
from backend.tests.test_review import group
from backend.tests.test_review import service as service  # 共用夹具
from backend.tests.test_review_purchase_price import CUSTOMS, ORDERS, SALES
from backend.tests.test_review_purchase_price import row as purchase_row
from backend.tests.test_source_storage import bundle, customs, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "盒"},
        {"quantity": Decimal("10332")},
        {"unit": "盒", "quantity": Decimal("10332")},
        {"unit": None, "quantity": None},
        {"unit": "12", "quantity": Decimal(0)},
    ],
)
def test_original_customs_unit_and_quantity_do_not_block_actual_comparable_prices(changes):
    purchases = [purchase_row(quantity="15000", gross="113000")]
    expected = declared_margin(CUSTOMS, purchases, ORDERS, SALES)
    result = declared_margin({**CUSTOMS, **changes}, purchases, ORDERS, SALES)
    assert result == expected
    assert result["status"] == "ok" and result["margin"] is not None
    assert auto_review_reasons("pending", False, 0, purchases, True, [result]) == []


def test_child_unit_code_does_not_override_parent_unit_name():
    purchases = [{**purchase_row(quantity="15000", gross="113000"), "unit": "12"}]
    result = declared_margin(CUSTOMS, purchases, ORDERS, SALES, unit_names={"12": "千克"})
    assert result["status"] == "ok"
    assert result["purchase"]["unit"] == "个"


def test_parent_unit_mismatch_blocks_even_when_child_and_customs_units_match():
    purchases = [{**purchase_row(quantity="15000", gross="113000"), "parent_purchase_unit": "盒"}]
    margin = declared_margin(CUSTOMS, purchases, ORDERS, SALES)
    assert (margin["status"], margin["margin"]) == ("unit_mismatch", None)
    assert margin["note"] == "母采购单对应明细的采购单位与报关单位不一致，不计算申报幅度"
    assert margin["purchase"]["unit"] == "盒" and margin["purchase"]["usd"] is not None
    assert not margin_alert([margin])
    reasons = auto_review_reasons("pending", False, 0, purchases, True, [margin])
    assert reasons == ["报关或关联子采购口径不一致：" + margin["note"]]


@pytest.mark.parametrize(
    "child_unit,parent_unit,status", [("千克", "包", "unit_mismatch"), ("卷", "千克", "ok")]
)
def test_page_displays_and_checks_parent_line_unit_instead_of_child_unit(
    ns, engine, service, child_unit, parent_unit, status
):
    order = purchase()
    declaration = customs("870", original=(Decimal("10"), "卷"))
    for _, record in order[2]:
        record["custrecord_swc_subpo_item_unit"] = child_unit
        record["custrecord_swc_subpo_item_bgunit"] = "千克"
    for _, record in declaration[2]:
        record["custrecord_swc_delare_unit"] = "千克"
    data = bundle([order], [declaration])
    for parent in data["relation_evidence"]["870"]["parentLines"]:
        parent["unitname"] = parent_unit
    save(ns, engine, data)
    shown = group(service, "CD870")
    assert all(line.marginStatus == status for line in shown.customsLines)
    assert all(line.originalPriceUnit == parent_unit for line in shown.customsLines)
    assert all(line.declaredPriceUnit == "千克" for line in shown.customsLines)
    assert shown.unitMismatch is (status == "unit_mismatch")
    assert shown.autoReview.eligible is (status == "ok")


def test_missing_parent_unit_blocks_margin_even_when_child_unit_matches():
    purchases = [purchase_row(quantity="15000", gross="113000")]
    purchases[0].pop("parent_purchase_unit")
    result = declared_margin(CUSTOMS, purchases, ORDERS, SALES)
    assert result["status"] == "unavailable" and result["margin"] is None
    assert result["purchase"]["unit"] == "" and result["purchase"]["usd"] is not None
    assert "母采购" in result["note"]


def test_every_linked_parent_line_must_use_the_declared_unit():
    purchases = [
        {**purchase_row(), "parent_purchase_unit": "个"},
        {**purchase_row(2, 2, quantity="6000"), "parent_purchase_unit": "包"},
    ]
    result = declared_margin(CUSTOMS, purchases, ORDERS, SALES)
    assert result["status"] == "unit_mismatch" and result["margin"] is None
    assert result["purchase"]["unit"] == "个、包"


def test_partly_missing_parent_units_block_margin_and_display_only_known_units():
    purchases = [
        {**purchase_row(), "parent_purchase_unit": ""},
        {**purchase_row(2, 2, quantity="6000"), "parent_purchase_unit": "个"},
    ]
    result = declared_margin(CUSTOMS, purchases, ORDERS, SALES)
    assert result["status"] == "unavailable" and result["margin"] is None
    assert result["purchase"]["unit"] == "个"


def test_review_page_uses_actual_units_and_removes_false_mismatch_from_filter(ns, engine, service):
    save(ns, engine, bundle([purchase()], [customs("870", original=(Decimal("5"), "千克"))]))
    result = group(service, "CD870")
    line = result.customsLines[0]
    assert (line.originalQuantity, line.originalPriceUnit, line.originalPrice) == ("5", "个", "1.252676")
    assert (line.quantity, line.unit) == ("10", "个")
    assert line.marginStatus == "ok" and line.margin
    assert not result.unitMismatch and not result.marginAlert and result.autoReview.eligible
    filtered = service.browse(DeclarationListQuery(status="unit_mismatch"))
    assert filtered.counts["unitMismatch"] == filtered.total == 0
