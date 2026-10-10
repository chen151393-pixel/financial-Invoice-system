"""数据库来源的逐行展示：跨品名、同名歧义、母行键、失效依据与审核摘要。"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime

import pytest
from backend.core.errors import ApiError
from backend.modules.business import relation_dao
from backend.modules.business.relation_entity import RELATION_TABLE, define_relation_table
from backend.modules.business.relation_mapper import summarize_relations
from backend.modules.business.relation_storage_mapper import relation_values
from backend.modules.business.review_source_mapper import review_sources
from backend.modules.business.storage_service import StorageService
from backend.modules.reconciliation.dto import ApproveRequest, DeclarationListQuery
from backend.modules.reconciliation.local_mapper import declarations
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.source.policy.local_relation_policy import local_line_relations
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select


def source(record_type, identity, line_type, record, rows):
    return {
        "recordType": record_type,
        "recordId": identity,
        "lineType": line_type,
        "record": record,
        "lines": [{"id": key, "record": value} for key, value in rows.items()],
    }


@pytest.fixture
def sample():
    stamp = datetime(2026, 9, 24)
    head = {
        "id": 1,
        "tenant_id": "owner",
        "ns_account": "prod",
        "ns_internal_id": "870",
        "record_no": "CD000870",
        "declaration_no": "REAL",
        "synced_at": stamp,
    }
    order = {
        "id": 2,
        "tenant_id": "owner",
        "ns_account": "prod",
        "ns_internal_id": "200",
        "customs_declaration_id": 1,
        "order_no": "CHILD",
        "parent_order_no": "PARENT",
        "pl_no": "PL001",
        "supplier_name": "供应商",
        "currency_code": "CNY",
    }
    order_record = {
        "custrecord_swc_subpo_baoguannum": {"id": "870"},
        "custrecord_swc_subpo_class": {"id": "3"},
        "custrecord_swc_subpo_plnum": {"id": "783"},
        "custrecord_swc_subpo_mainpo": {"id": "100"},
        "custrecord_swc_subpo_so": {"id": "90"},
    }
    summaries, raw_lines, details, lines, packing, parents, links = {}, {}, [], [], [], [], []
    for i, name in enumerate(("墨水", "清洗液", "热熔粉", "相纸"), 1):
        key = str(i)
        summaries[key] = {
            "custrecord_swc_relate_record": {"id": "870"},
            "custrecord_swc_company": {"id": "3"},
            "custrecord_swc_delare_name": name,
            "custrecord_swc_goods_place": {"id": "10"},
        }
        details.append(
            {
                "id": i,
                "customs_declaration_id": 1,
                "source_line_key": f"customrecord_swc_delare_detail:{i}",
                "line_no": i,
                "declaration_name": name,
                "specification": "型号",
                "declared_quantity": "5.00",
                "declared_unit": "千克",
                "unit_price": "10",
                "amount": "50",
                "currency_code": "USD",
                "pl_no": "PL001",
                "company_name": "申报公司",
            }
        )
        raw_lines[key] = {
            "custrecord_swc_subpo_main": {"id": "200"},
            "custrecord_swc_subpo_item_item": {"id": key},
            "custrecord_swc_subpo_item_mainpo_lineid": key,
            "custrecord_swc_subpo_item_ifreqid": {"id": "50"},
            "custrecord_swc_subpo_item_solineid": key,
            "custrecord_swc_subpo_item_bgname": name,
        }
        lines.append(
            {
                "id": 100 + i,
                "purchase_order_id": 2,
                "source_line_key": f"customrecord_swc_subpo_item:{i}",
                "item_name": "普通商品名",
                "declaration_name": name,
                "specification": "",
                "quantity": "500",
                "unit_name": "包",
                "declaration_quantity": "5.00",
                "declaration_unit": "千克",
                "tax_inclusive_price": "0.2",
                "amount": "9007199254740993.01",
            }
        )
        packing.append(
            {
                "id": key,
                "custrecord_swc_declare_record": "870",
                "custrecord_swc_sublist_packingmain": "783",
                "custrecord_swc_sublist_purchaseorderhead": "3",
                "custrecord_swc_sublist_protranid": "100",
                "custrecord_swc_sublist_itemid": key,
                "custrecord_swc_sublist_createdfrom": "90",
                "custrecord_swc_so_lineid": key,
                "custrecord_swc_sublist_fulreq_tranid": "50",
                "custrecord_swc_sublist_purchasesource": "10",
            }
        )
        parents.append({"transaction": "100", "id": key, "item": key, "mainline": "F", "taxline": "F"})
        links.append(
            {
                "nextdoc": "100",
                "nextline": key,
                "previousdoc": "90",
                "previousline": key,
                "nexttype": "PurchOrd",
                "previoustype": "SalesOrd",
            }
        )
    head["source_data"] = source(
        "customrecord_swc_declare_record", "870", "customrecord_swc_delare_detail", {}, summaries
    )
    order["source_data"] = source(
        "customrecord_swc_subpo", "200", "customrecord_swc_subpo_item", order_record, raw_lines
    )
    evidence = {
        "version": 1,
        "account": "prod",
        "declarationId": "870",
        "status": "partial",
        "issues": [],
        "mode": "evidence_backfill",
        "baseSyncedAt": stamp.isoformat(),
        "packingLines": packing,
        "parentLines": parents,
        "purchaseLinks": links,
    }
    return head, details, [order], lines, evidence


def transformed(sample):
    head, details, purchases, lines, evidence = sample
    return review_sources(
        summarize_relations(
            {
                "heads": [head],
                "details": details,
                "purchases": purchases,
                "lines": lines,
                "relation_results": [
                    {"customs_declaration_id": head["id"], **relation_values(head, evidence)}
                ],
            }
        )
    )


def test_groups_keep_each_purchase_under_its_customs_row_and_original_amount(sample):
    data = transformed(sample)
    group = declarations(data)[0]
    assert group.purchaseCount == 4 and not group.unlinkedLines
    for row in group.customsLines:
        assert row.purchaseCount == 1
        assert row.purchaseLines[0].name == row.name
        assert row.purchaseLines[0].scope == "order"
        assert row.purchaseLines[0].quantity == "5.00"
        assert row.purchaseLines[0].amount == "9007199254740993.01"
    assert "source_data" not in data["heads"][0]
    assert "source_data" not in data["purchases"][0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("custrecord_swc_declare_record", "OTHER"),
        ("custrecord_swc_sublist_packingmain", "OTHER"),
        ("custrecord_swc_sublist_purchaseorderhead", "OTHER"),
        ("custrecord_swc_sublist_protranid", "OTHER"),
        ("custrecord_swc_sublist_itemid", "OTHER"),
        ("custrecord_swc_sublist_fulreq_tranid", "OTHER"),
        ("custrecord_swc_sublist_purchasesource", "OTHER"),
        ("isinactive", "T"),
    ],
)
def test_name_alone_cannot_attach_a_purchase_with_conflicting_source(sample, field, value):
    sample[4]["packingLines"][0][field] = value
    group = declarations(transformed(sample))[0]
    assert group.customsLines[0].purchaseCount == 0
    assert len(group.unlinkedLines) == 1 and group.unlinkedLines[0].name == "墨水"
    assert all(row.purchaseCount == 1 for row in group.customsLines[1:])


def test_duplicate_summary_is_ambiguous_but_distinct_origin_disambiguates(sample):
    head, details, _, _, _ = sample
    raw = deepcopy(head["source_data"]["lines"][0])
    raw["id"] = "5"
    head["source_data"]["lines"].append(raw)
    details.append({**details[0], "id": 5, "source_line_key": "customrecord_swc_delare_detail:5"})
    assert "101" not in local_line_relations(*sample)
    raw["record"]["custrecord_swc_goods_place"] = {"id": "70"}
    assert local_line_relations(*sample)["101"] == "1"
    second_pack = deepcopy(sample[4]["packingLines"][0])
    second_pack.update(id="5", custrecord_swc_sublist_purchasesource="70")
    sample[4]["packingLines"].append(second_pack)
    assert "101" not in local_line_relations(*sample)  # 不能把整条子采购复制给两个报关行。


@pytest.mark.parametrize(
    "change", ["parent_key", "sales_link", "bgname", "snapshot", "dependency", "account", "tenant"]
)
def test_missing_or_stale_evidence_does_not_fall_back_to_product_name(sample, change):
    head, _, purchases, _, evidence = sample
    if change == "parent_key":
        evidence["parentLines"][0]["id"] = "999"
    elif change == "sales_link":
        evidence["purchaseLinks"].clear()
    elif change == "bgname":
        purchases[0]["source_data"]["lines"][0]["record"].pop("custrecord_swc_subpo_item_bgname")
    elif change == "snapshot":
        head["synced_at"] = datetime(2026, 9, 25)
    elif change == "dependency":
        evidence["mode"] = "dependency_changed"
    else:
        purchases[0]["ns_account" if change == "account" else "tenant_id"] = "OTHER"
    assert "101" not in local_line_relations(*sample)


def test_no_parent_requires_fulfillment_and_sales_line_refs(sample):
    _, _, purchases, _, evidence = sample
    purchases[0]["source_data"]["record"].pop("custrecord_swc_subpo_mainpo")
    for pack in evidence["packingLines"]:
        pack.pop("custrecord_swc_sublist_protranid")
    assert len(local_line_relations(*sample)) == 4
    purchases[0]["source_data"]["lines"][0]["record"].pop("custrecord_swc_subpo_item_ifreqid")
    assert "101" not in local_line_relations(*sample)


def test_changed_row_assignment_invalidates_review_content_digest(sample):
    before = transformed(sample)["review_sources"][1]
    sample[4]["packingLines"][0]["custrecord_swc_sublist_purchasesource"] = "70"
    after = transformed(sample)["review_sources"][1]
    assert before["digest"] != after["digest"]
    assert before["content"]["lineRelations"]["101"] == "1"
    assert "101" not in after["content"]["lineRelations"]


def test_review_rejects_changed_row_assignment_even_when_amounts_are_unchanged(sample, context):
    class Source:
        def read(self, owner, **criteria):
            return {
                **transformed(sample),
                "total": 1,
                "accounts": ["prod"],
                "counts": {"all": 1, "pending": 1, "approved": 0, "blocked": 0},
            }

        @contextmanager
        def locked_review(self, owner, account, declaration_id):
            yield self.read(owner)

    service = ReconciliationService(context.settings, None, context.engine, Source())
    group = service.browse(DeclarationListQuery(), "user:admin").groups[0]
    assert group.review.allowed and group.customsLines[0].purchaseCount == 1
    sample[4]["packingLines"][0]["custrecord_swc_sublist_purchasesource"] = "70"
    with pytest.raises(ApiError, match="已更新") as error:
        service.approve(ApproveRequest(snapshotId=group.snapshotId), "user:admin")
    assert error.value.status == 409
    latest = service.browse(DeclarationListQuery(), "user:admin").groups[0]
    assert latest.review.status == "pending" and len(latest.unlinkedLines) == 1
    assert latest.unlinkedLines[0].amount == group.customsLines[0].purchaseLines[0].amount


def test_independent_child_update_invalidates_saved_packing_even_without_v3(sample):
    metadata = MetaData()
    customs = Table(
        "customs_declarations",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tenant_id", String),
        Column("ns_account", String),
        Column("ns_internal_id", String),
        Column("record_no", String),
        Column("is_active", Integer),
    )
    purchase = Table(
        "purchase_orders",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tenant_id", String),
        Column("ns_account", String),
        Column("ns_internal_id", String),
        Column("customs_declaration_id", Integer),
    )
    table = define_relation_table(metadata)
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    head, _, _, _, evidence = sample
    tables = {customs.name: customs, purchase.name: purchase, RELATION_TABLE: table}
    try:
        with engine.begin() as connection:
            for identity, tenant in [(1, "owner"), (2, "other")]:
                current = {**head, "id": identity, "tenant_id": tenant, "is_active": 1}
                connection.execute(customs.insert().values(**{key: current[key] for key in customs.c.keys()}))
                connection.execute(
                    purchase.insert().values(
                        id=identity,
                        tenant_id=tenant,
                        ns_account="prod",
                        ns_internal_id="200",
                        customs_declaration_id=identity,
                    )
                )
                relation_dao.save_result(connection, table, relation_values(current, evidence))
            StorageService(None, engine)._invalidate_previous_relations(
                connection,
                tables,
                {"customs": [], "purchase": [{"head": {"ns_internal_id": "200"}}]},
                "owner",
                "prod",
            )
            modes = dict(connection.execute(select(table.c.tenant_id, table.c.mode)).all())
            assert modes == {"owner": "dependency_changed", "other": "evidence_backfill"}
    finally:
        engine.dispose()
