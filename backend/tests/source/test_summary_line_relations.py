"""同名冷裱膜：原始单位消歧与子采购报关数量、单位消歧，使用合成数据。"""

from copy import deepcopy
from decimal import Decimal

import pytest
from backend.core.events import EventBus
from backend.modules.review.dto.review_dto import DeclarationListQuery
from backend.modules.source.policy.local_relation_policy import local_line_relations
from backend.modules.source.public import DeclarationService
from backend.tests.review_helpers import MaterializedReviewService
from backend.tests.test_source_storage import bundle, customs, declaration, purchase, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns


@pytest.fixture
def films():
    order, head = purchase(), customs()
    data = bundle([order], [head])
    evidence = data["relation_evidence"]["870"]
    for index, (unit, label, quantity, amount, model) in enumerate(
        [("17", "包", "8000", "51920", "A4(210×297mm)×20张"), ("20", "卷", "512", "36700.16", "0.305×50m")]
    ):
        key = str(index + 1)
        child, summary = order[2][index][1], head[2][index][1]
        child.update(
            custrecord_swc_subpo_item_bgname="冷裱膜",
            custrecord_swc_subpo_item_bgunit={"id": unit, "refName": label},
            custrecord_swc_subpo_item_bgqty=Decimal(quantity),
            custrecord_swc_subpo_item_amountwithtax=Decimal(amount),
        )
        summary.update(
            custrecord_swc_delare_name="冷裱膜",
            custrecord_swc_delare_unit={"id": unit, "refName": label},
            custrecord_swc_delare_quantity=Decimal(quantity),
            custrecord_swc_huge=model,
        )
        evidence["rawLines"].append(
            {
                "id": f"900{key}",
                "declarationId": "870",
                "plId": "783",
                "packingId": f"870{key}",
                "companyId": "3",
                "itemId": key,
                "parentPurchaseId": "100",
                "fulfillmentId": "50",
                "fulfillmentLine": key,
                "name": "冷裱膜",
                "declarationUnitId": unit,
            }
        )
        evidence["packingLines"][index]["custrecord_swc_sublist_fulreq_lineid"] = key
    return data


def bindings(data):
    """直接调用生产 policy，隔离验证来源身份，不连接数据库。"""

    def source(record_type, line_type, document):
        identity, record, lines = document
        return {
            "recordType": record_type,
            "recordId": identity,
            "lineType": line_type,
            "record": record,
            "lines": [{"id": key, "record": row} for key, row in lines],
        }

    head = {
        "ns_internal_id": "870",
        "ns_account": "prod",
        "tenant_id": "",
        "source_data": source(
            "customrecord_swc_declare_record", "customrecord_swc_delare_detail", data["customs"][0]
        ),
    }
    details = [
        {"id": index + 1, "source_line_key": f"customrecord_swc_delare_detail:{key}"}
        for index, (key, _) in enumerate(data["customs"][0][2])
    ]
    order = {
        "id": 1,
        "ns_internal_id": "200",
        "ns_account": "prod",
        "tenant_id": "",
        "source_data": source("customrecord_swc_subpo", "customrecord_swc_subpo_item", data["purchases"][0]),
    }
    lines = [
        {"id": index + 11, "purchase_order_id": 1, "source_line_key": f"customrecord_swc_subpo_item:{key}"}
        for index, (key, _) in enumerate(data["purchases"][0][2])
    ]
    return local_line_relations(
        head, details, [order], lines, {**data["relation_evidence"]["870"], "mode": "full_sync"}
    )


def test_same_name_distinct_original_units_bind_to_separate_summaries(films):
    assert bindings(films) == {"11": "1", "12": "2"}


def test_suiteql_scalar_units_match_rest_reference_units(films):
    for _, row in films["customs"][0][2]:
        row["custrecord_swc_delare_unit"] = row["custrecord_swc_delare_unit"]["id"]
    assert bindings(films) == {"11": "1", "12": "2"}


def test_inactive_original_cannot_resolve_ambiguity(films):
    films["relation_evidence"]["870"]["rawLines"][0]["isInactive"] = True
    assert bindings(films) == {"12": "2"}


def test_uses_original_unit_not_purchase_unit_or_model(films):
    for _, row in films["purchases"][0][2]:
        row["custrecord_swc_subpo_item_bgunit"] = {"id": "99", "refName": "箱"}
    for _, row in films["customs"][0][2]:
        row["custrecord_swc_huge"] = "相同规格"
    assert bindings(films) == {"11": "1", "12": "2"}


@pytest.mark.parametrize(
    "case",
    [
        "missing_unit",
        "unknown_unit",
        "duplicate_unit",
        "missing_summary_unit",
        "same_labels_different_ids",
    ],
)
def test_missing_or_ambiguous_units_never_guess(films, case):
    evidence = films["relation_evidence"]["870"]
    if case in ("missing_unit", "unknown_unit"):
        for raw in evidence["rawLines"]:
            raw["declarationUnitId"] = "" if case == "missing_unit" else "99"
    elif case == "duplicate_unit":
        films["customs"][0][2][1][1]["custrecord_swc_delare_unit"] = {"id": "17"}
    elif case == "missing_summary_unit":
        del films["customs"][0][2][1][1]["custrecord_swc_delare_unit"]
    else:
        for _, row in films["customs"][0][2]:
            row["custrecord_swc_delare_unit"]["id"] = "99"
    assert bindings(films) == {}


@pytest.mark.parametrize(
    "field",
    [
        "declarationId",
        "plId",
        "packingId",
        "companyId",
        "itemId",
        "parentPurchaseId",
        "fulfillmentId",
        "fulfillmentLine",
        "name",
    ],
)
def test_wrong_original_identity_cannot_bind(films, field):
    films["relation_evidence"]["870"]["rawLines"][0][field] = "wrong"
    assert bindings(films) == {"12": "2"}


def test_missing_packing_reference_requires_unique_full_source(films):
    evidence = films["relation_evidence"]["870"]
    evidence["rawLines"][0]["packingId"] = ""
    assert bindings(films) == {"11": "1", "12": "2"}
    duplicate = deepcopy(evidence["packingLines"][0])
    duplicate["id"] = "999"
    evidence["packingLines"].append(duplicate)
    assert bindings(films) == {"12": "2"}


def test_one_purchase_line_spanning_two_summaries_stays_unlinked(films):
    evidence = films["relation_evidence"]["870"]
    other = deepcopy(evidence["rawLines"][0])
    other.update(id="999", declarationUnitId="20")
    evidence["rawLines"].append(other)
    assert bindings(films) == {"12": "2"}


def test_unique_old_binding_is_not_rejected_by_changed_unit(films):
    for index, (_, row) in enumerate(films["customs"][0][2]):
        row["custrecord_swc_delare_name"] = f"产品{index}"
        films["purchases"][0][2][index][1]["custrecord_swc_subpo_item_bgname"] = f"产品{index}"
    films["relation_evidence"]["870"]["rawLines"] = []
    assert bindings(films) == {"11": "1", "12": "2"}


def test_resync_rebuilds_links_and_review_without_duplicating_amounts(ns, engine, films):
    old = deepcopy(films)
    old["relation_evidence"]["870"]["rawLines"] = []
    for _, row in old["purchases"][0][2]:
        row["custrecord_swc_subpo_item_bgqty"] += Decimal("1")
    save(ns, engine, old)
    before = declaration(engine)["content_sha256"]
    save(ns, engine, films)
    after = declaration(engine)["content_sha256"]
    assert after != before
    link_query = (
        "SELECT id, purchase_line_id, customs_line_id, evidence "
        "FROM source_customs_purchase_links WHERE status = 'active' ORDER BY id"
    )
    links = rows(engine, link_query)
    assert len(links) == 3  # 一条单头关联与两条明细关联
    review = MaterializedReviewService(engine, DeclarationService(engine), EventBus())
    result = review.browse(DeclarationListQuery()).groups[0]
    assert result.unlinkedLines == []
    assert [r.purchaseCount for r in result.customsLines] == [1, 1]
    assert [r.purchaseLines[0].quantity for r in result.customsLines] == ["8000", "512"]
    assert [r.purchaseLines[0].amount for r in result.customsLines] == ["51920", "36700.16"]
    saved = DeclarationService(engine).detail(int(result.id))["evidence"]
    assert {entry["originalUnitId"] for entry in saved["localLineDiagnostics"]} == {"17", "20"}
    assert all(entry["code"] == "RAW_SUMMARY_UNIT_CANDIDATE" for entry in saved["localLineDiagnostics"])
    save(ns, engine, films)
    assert declaration(engine)["content_sha256"] == after
    assert rows(engine, link_query) == links


def test_lost_unit_evidence_invalidates_previous_line_link(ns, engine, films):
    save(ns, engine, films)
    films["relation_evidence"]["870"]["rawLines"][0]["declarationUnitId"] = ""
    save(ns, engine, films)
    links = rows(engine, "SELECT * FROM source_customs_purchase_links WHERE evidence = 'local_packing'")
    assert sorted(link["status"] for link in links) == ["active", "stale"]


def test_missing_originals_bind_using_purchase_units_and_quantities(films):
    films["relation_evidence"]["870"]["rawLines"] = []
    assert bindings(films) == {"11": "1", "12": "2"}


def test_split_purchase_rows_are_summed_once_despite_repeated_packing(films):
    evidence = films["relation_evidence"]["870"]
    evidence["rawLines"] = []
    child_rows = films["purchases"][0][2]
    first = child_rows[0][1]
    first["custrecord_swc_subpo_item_bgqty"] = Decimal("3000.1")
    second = deepcopy(first)
    second["custrecord_swc_subpo_item_bgqty"] = Decimal("4999.9")
    child_rows.append(("extra", second))
    # 多个 Packing 引用不应把同一条子采购的数量重复加总。
    pack = deepcopy(evidence["packingLines"][0])
    pack["id"] = "another"
    evidence["packingLines"].append(pack)
    assert bindings(films) == {"11": "1", "12": "2", "13": "1"}


@pytest.mark.parametrize("quantity", [None, "NaN", "Infinity", "wrong", "0", "-8000", "7999.99"])
def test_invalid_or_unequal_purchase_quantity_stays_unlinked(films, quantity):
    films["relation_evidence"]["870"]["rawLines"] = []
    films["purchases"][0][2][0][1]["custrecord_swc_subpo_item_bgqty"] = quantity
    assert bindings(films) == {"12": "2"}


@pytest.mark.parametrize("unit", ["", "99"])
def test_missing_or_different_purchase_unit_is_not_inferred_from_quantity(films, unit):
    films["relation_evidence"]["870"]["rawLines"] = []
    films["purchases"][0][2][0][1]["custrecord_swc_subpo_item_bgunit"] = unit
    assert bindings(films) == ({} if not unit else {"12": "2"})


def test_duplicate_summary_quantity_and_unit_stays_ambiguous(films):
    films["relation_evidence"]["870"]["rawLines"] = []
    duplicate = deepcopy(films["customs"][0][2][0][1])
    films["customs"][0][2].append(("duplicate", duplicate))
    assert bindings(films) == {"12": "2"}


def test_same_unit_groups_require_total_quantity_match(films):
    films["relation_evidence"]["870"]["rawLines"] = []
    films["purchases"][0][2][1][1]["custrecord_swc_subpo_item_bgunit"] = "17"
    # 不能先将 8000 那条单独匹配；该单位真实合计为 8512。
    assert bindings(films) == {}


def test_cross_origin_purchase_cannot_be_counted_in_either_group(films):
    evidence = films["relation_evidence"]["870"]
    evidence["rawLines"] = []
    pack = deepcopy(evidence["packingLines"][0])
    pack.update(id="other", custrecord_swc_sublist_purchasesource="another-origin")
    evidence["packingLines"].append(pack)
    assert bindings(films) == {}


def test_no_originals_sync_persists_review_links_and_invalidates_on_quantity_change(ns, engine, films):
    films["relation_evidence"]["870"]["rawLines"] = []
    save(ns, engine, films)
    review = MaterializedReviewService(engine, DeclarationService(engine), EventBus())
    result = review.browse(DeclarationListQuery()).groups[0]
    assert result.unlinkedLines == []
    assert [r.purchaseLines[0].quantity for r in result.customsLines] == ["8000", "512"]
    assert [r.purchaseLines[0].amount for r in result.customsLines] == ["51920", "36700.16"]
    saved = DeclarationService(engine).detail(int(result.id))["evidence"]
    assert {entry["code"] for entry in saved["localLineDiagnostics"]} == {"PURCHASE_SUMMARY_UNIT_QUANTITY"}
    digest = declaration(engine)["content_sha256"]
    save(ns, engine, films)
    assert declaration(engine)["content_sha256"] == digest
    films["purchases"][0][2][0][1]["custrecord_swc_subpo_item_bgqty"] = Decimal("7999")
    save(ns, engine, films)
    links = rows(engine, "SELECT * FROM source_customs_purchase_links WHERE evidence = 'local_packing'")
    assert sorted(link["status"] for link in links) == ["active", "stale"]
