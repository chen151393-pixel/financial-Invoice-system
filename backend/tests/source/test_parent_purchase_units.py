"""母采购单位按原生单据、行号及货品核实，使用合成来源快照。"""

from copy import deepcopy

import pytest
from backend.modules.source.mapper.parent_purchase_unit_mapper import parent_purchase_units


def source():
    orders = [
        {
            "id": 1,
            "ns_internal_id": "200",
            "raw_payload": {
                "recordType": "customrecord_swc_subpo",
                "recordId": "200",
                "record": {"custrecord_swc_subpo_mainpo": {"id": "100"}},
                "lineType": "customrecord_swc_subpo_item",
                "lines": [
                    {
                        "id": "201",
                        "record": {
                            "custrecord_swc_subpo_item_mainpo_lineid": "1",
                            "custrecord_swc_subpo_item_item": {"id": "1270"},
                        },
                    }
                ],
            },
        }
    ]
    lines = [
        {
            "id": 11,
            "purchase_order_id": 1,
            "source_line_key": "customrecord_swc_subpo_item:201",
            "quantity": "4000",
            "unit": "千克",
            "declared_quantity": "1184",
            "declared_unit": "千克",
        }
    ]
    evidence = {
        "parentLines": [
            {
                "transaction": "100",
                "id": "1",
                "item": "1270",
                "mainline": "F",
                "taxline": "F",
                "units": "18",
                "unitname": "包",
            }
        ]
    }
    return orders, lines, evidence


def test_unit_comes_from_parent_line_and_keeps_child_quantity_and_unit():
    data = source()
    before = deepcopy(data)
    (line,) = parent_purchase_units(*data)
    assert line["parent_purchase_unit"] == "包" and not line["parent_purchase_unit_issue"]
    assert line["unit"] == "千克" and line["quantity"] == "4000"
    assert data == before


@pytest.mark.parametrize(
    "changes",
    [
        {"transaction": "999"},
        {"id": "2"},
        {"item": "1271"},
        {"mainline": "T"},
        {"taxline": "T"},
    ],
)
def test_other_parent_or_item_and_non_item_lines_cannot_supply_unit(changes):
    orders, lines, evidence = source()
    evidence["parentLines"][0].update(changes)
    (line,) = parent_purchase_units(orders, lines, evidence)
    assert line["parent_purchase_unit"] == ""
    assert "缺失或不唯一" in line["parent_purchase_unit_issue"]


def test_repeated_item_is_resolved_by_native_line_id_and_duplicates_are_unavailable():
    orders, lines, evidence = source()
    original = evidence["parentLines"][0]
    evidence["parentLines"].append({**original, "id": "2", "unitname": "卷"})
    orders[0]["raw_payload"]["lines"][0]["record"]["custrecord_swc_subpo_item_mainpo_lineid"] = "2"
    assert parent_purchase_units(orders, lines, evidence)[0]["parent_purchase_unit"] == "卷"
    evidence["parentLines"].append({**evidence["parentLines"][1]})
    (line,) = parent_purchase_units(orders, lines, evidence)
    assert line["parent_purchase_unit"] == "" and "不唯一" in line["parent_purchase_unit_issue"]


@pytest.mark.parametrize("missing", ["parent", "line", "item", "raw", "evidence"])
def test_missing_parent_evidence_returns_specific_reason_without_child_unit_fallback(missing):
    orders, lines, evidence = source()
    raw = orders[0]["raw_payload"]
    if missing == "parent":
        raw["record"]["custrecord_swc_subpo_mainpo"] = None
    elif missing == "line":
        raw["lines"][0]["record"].pop("custrecord_swc_subpo_item_mainpo_lineid")
    elif missing == "item":
        raw["lines"][0]["record"].pop("custrecord_swc_subpo_item_item")
    elif missing == "raw":
        orders[0]["raw_payload"] = None
    else:
        evidence = None
    (line,) = parent_purchase_units(orders, lines, evidence)
    assert line["parent_purchase_unit"] == "" and line["parent_purchase_unit_issue"]


@pytest.mark.parametrize("unit", ["18", 18, None])
def test_old_snapshot_without_parent_unit_name_needs_resync(unit):
    orders, lines, evidence = source()
    evidence["parentLines"][0].update(units=unit, unitname=None)
    (line,) = parent_purchase_units(orders, lines, evidence)
    assert line["parent_purchase_unit"] == ""
    assert "重新同步母采购行依据" in line["parent_purchase_unit_issue"]


@pytest.mark.parametrize("unit", [" 卷 ", {"id": "18", "refName": "卷"}])
def test_legacy_snapshot_with_explicit_native_unit_name_can_be_reused(unit):
    orders, lines, evidence = source()
    evidence["parentLines"][0].update(units=unit, unitname=None)
    (line,) = parent_purchase_units(orders, lines, evidence)
    assert line["parent_purchase_unit"] == "卷" and not line["parent_purchase_unit_issue"]
