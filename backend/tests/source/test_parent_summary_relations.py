"""Packing 缺失的本地快照：双方母采购引用、报关单位与完整数量组交叉核验。"""

from copy import deepcopy
from decimal import Decimal

import pytest
from backend.app import create_events
from backend.modules.review.dto.review_dto import DeclarationListQuery
from backend.modules.review.service.calculation_service import CalculationService
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService
from backend.modules.source.service import link_service
from backend.modules.source.service.relation_rebuild_service import RelationRebuildService
from backend.tests.source.test_summary_line_relations import bindings
from backend.tests.source.test_summary_line_relations import films as films
from backend.tests.test_source_storage import declaration, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns


@pytest.fixture
def no_packing(films):
    evidence = films["relation_evidence"]["870"]
    for key in ("rawLines", "packingLines", "purchaseLinks"):
        evidence[key] = []
    for _, summary in films["customs"][0][2]:
        summary.update(
            custrecord_swc_purachse_no={"id": "100"},
            custrecord_swc_salesorder_number={"id": "90"},
            custrecord_swc_packing_no={"id": "783"},
        )
    return films


def test_explicit_parent_reference_resolves_without_packing(no_packing):
    assert bindings(no_packing) == {"11": "1", "12": "2"}


@pytest.mark.parametrize(
    "field",
    [
        "custrecord_swc_relate_record",
        "custrecord_swc_purachse_no",
        "custrecord_swc_salesorder_number",
        "custrecord_swc_packing_no",
        "custrecord_swc_company",
        "custrecord_swc_delare_name",
        "custrecord_swc_delare_unit",
    ],
)
def test_summary_reference_mismatch_is_not_replaced_by_equal_quantity(no_packing, field):
    no_packing["customs"][0][2][0][1][field] = "wrong"
    assert bindings(no_packing) == {"12": "2"}


@pytest.mark.parametrize(
    "field",
    [
        "custrecord_swc_subpo_item_item",
        "custrecord_swc_subpo_item_mainpo_lineid",
        "custrecord_swc_subpo_main",
    ],
)
def test_child_must_identify_its_real_parent_line(no_packing, field):
    no_packing["purchases"][0][2][0][1][field] = "wrong"
    assert bindings(no_packing) == {"12": "2"}


def test_missing_parent_lines_cannot_use_header_alone(no_packing):
    no_packing["relation_evidence"]["870"]["parentLines"] = []
    assert bindings(no_packing) == {}


@pytest.mark.parametrize("field", ["custrecord_swc_goods_place", "custrecord_swc_delare_unit"])
def test_incomplete_summary_cannot_be_ignored_to_make_candidate_unique(no_packing, field):
    no_packing["customs"][0][2][0][1].pop(field)
    assert bindings(no_packing) == {}


@pytest.mark.parametrize("field", ["custrecord_swc_subpo_item_bgname", "custrecord_swc_subpo_item_bgunit"])
def test_incomplete_child_blocks_partial_group_matching(no_packing, field):
    no_packing["purchases"][0][2][0][1].pop(field)
    assert bindings(no_packing) == {}


def test_existing_conflicting_packing_never_uses_parent_fallback(no_packing):
    no_packing["relation_evidence"]["870"]["packingLines"] = [
        {"id": "1", "custrecord_swc_declare_record": "other"}
    ]
    assert bindings(no_packing) == {}


def test_same_parent_across_origins_is_ambiguous_even_if_quantity_differs(no_packing):
    duplicate = deepcopy(no_packing["customs"][0][2][0][1])
    duplicate.update(custrecord_swc_goods_place="another", custrecord_swc_delare_quantity=Decimal("1"))
    no_packing["customs"][0][2].append(("third", duplicate))
    assert bindings(no_packing) == {"12": "2"}


def test_same_name_other_parent_does_not_steal_child_lines(no_packing):
    duplicate = deepcopy(no_packing["customs"][0][2][0][1])
    duplicate["custrecord_swc_purachse_no"] = {"id": "different-parent"}
    no_packing["customs"][0][2].append(("third", duplicate))
    assert bindings(no_packing) == {"11": "1", "12": "2"}


def test_multiple_child_rows_require_full_group_total(no_packing):
    children = no_packing["purchases"][0][2]
    other = deepcopy(children[0][1])
    children[0][1]["custrecord_swc_subpo_item_bgqty"] = Decimal("3000.1")
    other["custrecord_swc_subpo_item_bgqty"] = Decimal("4999.9")
    children.append(("extra", other))
    assert bindings(no_packing) == {"11": "1", "12": "2", "13": "1"}
    other["custrecord_swc_subpo_item_bgqty"] = Decimal("4999.8")
    assert bindings(no_packing) == {"12": "2"}


def test_rule_upgrade_rebuilds_saved_v1_without_ns(ns, engine, no_packing, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(link_service, "local_line_relations", lambda *args, **kwargs: {})
        patch.setattr(link_service, "LOCAL_RELATION_VERSION", "purchase-unit-quantity-v1")
        save(ns, engine, no_packing)
    before = declaration(engine)
    original_lines = rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY id")
    events = create_events()
    rebuild = RelationRebuildService(engine, events)
    assert rebuild.rebuild()[0]["unlinkedLines"] == 0
    assert declaration(engine)["synced_at"] == before["synced_at"]
    assert rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY id") == original_lines
    review = ReviewService(engine, DeclarationService(engine), events)
    CalculationService(review).rebuild()
    group = review.browse(DeclarationListQuery()).groups[0]
    assert group.unlinkedLines == []
    assert [row.purchaseLines[0].amount for row in group.customsLines] == ["51920", "36700.16"]
    assert rebuild.rebuild()[0]["status"] == "current"
    content = DeclarationService(engine).detail(int(group.id))
    assert {r["code"] for r in content["evidence"]["localLineDiagnostics"]} == {
        "PARENT_SUMMARY_UNIT_QUANTITY"
    }
