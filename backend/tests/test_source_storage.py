"""source 模块保存到新表：映射、主数据、明细替换、关联、依据状态、内容摘要与版本保护。

使用 SQLite 隔离库与合成的 NS 数据包，不访问 NS。
"""

import json
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from backend.core.config import ROOT
from backend.core.database import make_engine
from backend.core.errors import ApiError
from backend.manage import upgrade_schema
from backend.modules.source.service.declaration_service import DeclarationService, digest, snapshot
from backend.modules.source.service.link_service import DEPENDENCY_ISSUE
from backend.modules.source.service.storage_service import StorageService
from sqlalchemy import text

ACCOUNT = "prod"
NAMES = ("墨水", "清洗液")


def config():
    mapping = json.loads((ROOT / "docs" / "netsuite-pl-lookup.json").read_text(encoding="utf-8"))
    # 示例配置的开票口径为采购单位 custrecord_swc_subpo_item_unit（2026-10-10 确认）。
    assert mapping["purchase_line"]["storage_fields"]["unit_name"] == "custrecord_swc_subpo_item_unit"
    mapping["customs"]["storage_fields"]["source_modified_at"] = "lastmodifieddate"
    return mapping


@pytest.fixture
def ns():
    mapping = config()
    types = [mapping[key]["type"] for key in ("pl", "purchase", "purchase_line", "customs", "customs_line")]
    return SimpleNamespace(settings=SimpleNamespace(pl_lookup=mapping, record_types=types, account=ACCOUNT))


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'source.sqlite'}")
    upgrade_schema(engine.url.render_as_string(hide_password=False))
    yield engine
    engine.dispose()


def purchase(order_id="200", customs_id="870", amounts=("100.50", "20.00")):
    head = {
        "id": order_id,
        "name": f"SUB-{order_id}",
        "custrecord_swc_subpo_trandate": "2026-09-01",
        "custrecord_swc_subpo_mainpo": {"id": "100", "refName": "PO-100"},
        "custrecord_swc_subpo_vendor": {"id": "77", "refName": "上海 供应商（有限）公司"},
        "custrecord_swc_subpo_total": Decimal("120.50"),
        "custrecord_swc_subpo_plnum": {"id": "783"},
        "custrecord_swc_subpo_baoguannum": {"id": customs_id},
        "custrecord_swc_subpo_class": {"id": "3", "refName": "采购公司A"},
        "custrecord_swc_subpo_so": {"id": "90"},
    }
    lines = []
    for index, (name, amount) in enumerate(zip(NAMES, amounts), 1):
        key = str(index)
        lines.append(
            (
                f"{order_id}{key}",
                {
                    "custrecord_swc_subpo_main": {"id": order_id},
                    "custrecord_swc_subpo_item_lineid": key,
                    "custrecord_swc_subpo_item_name": "普通商品名",
                    "custrecord_swc_subpo_item_bgname": name,
                    "custrecord_swc_subpo_item_qty": Decimal("10"),
                    "custrecord_swc_subpo_item_unit": "个",
                    "custrecord_swc_subpo_item_bgunit": "千克",
                    "custrecord_swc_subpo_item_bgqty": Decimal("5"),
                    "custrecord_swc_subpo_item_ratewithrate": Decimal("10.05"),
                    "custrecord_swc_subpo_item_amountwithtax": Decimal(amount) if amount else None,
                    # 行级定位依据（local_relation_policy）
                    "custrecord_swc_subpo_item_item": {"id": key},
                    "custrecord_swc_subpo_item_mainpo_lineid": key,
                    "custrecord_swc_subpo_item_ifreqid": {"id": "50"},
                    "custrecord_swc_subpo_item_solineid": key,
                },
            )
        )
    return order_id, head, lines


def customs(customs_id="870", modified="2026-09-02T10:00:00Z"):
    head = {
        "id": customs_id,
        "name": f"CD{customs_id}",
        "custrecord_swc_realno": f"REAL{customs_id}",
        "custrecord315": "2026-09-02",
        "custrecord_swc_piname": {"id": "8", "refName": "申报主体"},
        "lastmodifieddate": modified,
    }
    lines = []
    for index, name in enumerate(NAMES, 1):
        lines.append(
            (
                f"{customs_id}{index}",
                {
                    "custrecord_swc_relate_record": {"id": customs_id},
                    "custrecord_swc_salesorder_number": "SO1",
                    "custrecord_swc_goods_place": {"id": "10", "refName": "深圳"},
                    "custrecord_swc_delare_name": name,
                    "custrecord_swc_huge": "型号",
                    "custrecord_swc_quantity": Decimal("10"),
                    "custrecord_swc_unit": "个",
                    "custrecord_swc_delare_quantity": Decimal("5"),
                    "custrecord_swc_delare_unit": "千克",
                    "custrecord_swc_unitprice": Decimal("1.5"),
                    "custrecord_swc_grossamount": Decimal("15"),
                    "custrecord_swc_currency": "USD",
                    "custrecord_swc_packing_no": {"id": "783"},
                    "custrecord_swc_company": {"id": "3", "refName": "采购公司A"},
                },
            )
        )
    return customs_id, head, lines


def evidence(customs_id="870", status="matched"):
    packing, parents, links = [], [], []
    for index in range(1, len(NAMES) + 1):
        key = str(index)
        packing.append(
            {
                "id": f"{customs_id}{key}",
                "custrecord_swc_declare_record": customs_id,
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
    return {
        "version": 1,
        "account": ACCOUNT,
        "declarationId": customs_id,
        "status": status,
        "issues": [] if status == "matched" else ["部分原始报关行缺少可读取的Packing引用。"],
        "rawLines": [],
        "packingLines": packing,
        "purchaseLinks": links,
        "parentLines": parents,
    }


def bundle(purchases, declarations, with_evidence=True):
    return {
        "purchases": purchases,
        "customs": declarations,
        "warnings": [],
        "pl_names": {"783": "PL001"},
        "customs_purchase_membership": {
            customs_id: [
                order_id
                for order_id, head, _ in purchases
                if head["custrecord_swc_subpo_baoguannum"]["id"] == customs_id
            ]
            for customs_id, _, _ in declarations
        },
        "relation_evidence": {customs_id: evidence(customs_id) for customs_id, _, _ in declarations}
        if with_evidence
        else {},
    }


def save(ns, engine, data):
    return StorageService(ns, engine).save(lambda: deepcopy(data), read_relations=False)


def rows(engine, sql, **params):
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql), params).mappings()]


def declaration(engine, customs_id="870"):
    return rows(engine, "SELECT * FROM source_customs_declarations WHERE ns_internal_id = :i", i=customs_id)[
        0
    ]


def test_first_save_maps_rows_master_data_links_and_digest(ns, engine):
    result = save(ns, engine, bundle([purchase()], [customs()]))
    assert result["purchase"] == {"created": 1, "updated": 0, "linesCreated": 2, "linesUpdated": 0}
    assert result["customs"]["created"] == 1

    supplier = rows(engine, "SELECT * FROM source_suppliers")
    assert [(s["ns_internal_id"], s["name_normalized"]) for s in supplier] == [("77", "上海供应商(有限)公司")]
    companies = {c["ns_internal_id"]: c["name"] for c in rows(engine, "SELECT * FROM source_companies")}
    assert companies == {"classification:3": "采购公司A", "declarant:8": "申报主体"}

    order = rows(engine, "SELECT * FROM source_purchase_orders")[0]
    assert (order["order_no"], order["parent_order_no"], order["pl_no"]) == ("SUB-200", "PO-100", "PL001")
    lines = rows(engine, "SELECT * FROM source_purchase_order_lines ORDER BY source_line_key")
    assert [line["unit"] for line in lines] == ["个", "个"]  # 采购口径
    assert [line["declared_unit"] for line in lines] == ["千克", "千克"]
    assert Decimal(str(lines[0]["amount"])) == Decimal("100.50")
    assert lines[0]["item_name_normalized"] == "墨水" and lines[0]["amount_status"] == "matched"

    head = declaration(engine)
    assert head["relation_status"] == "complete" and head["content_sha256"]
    links = rows(engine, "SELECT * FROM source_customs_purchase_links WHERE status = 'active'")
    assert sorted(link["evidence"] for link in links) == ["local_packing", "local_packing", "ns_reference"]
    # 行级关联：同名报关行与子采购行一一对应
    customs_lines = {
        r["id"]: r["declaration_name"] for r in rows(engine, "SELECT * FROM source_customs_lines")
    }
    purchase_lines = {r["id"]: r["declaration_name"] for r in lines}
    for link in links:
        if link["evidence"] == "local_packing":
            assert customs_lines[link["customs_line_id"]] == purchase_lines[link["purchase_line_id"]]


def test_resave_same_content_keeps_digest_and_raw_records(ns, engine):
    data = bundle([purchase()], [customs()])
    save(ns, engine, data)
    first = declaration(engine)["content_sha256"]
    raw_count = len(rows(engine, "SELECT id FROM source_raw_records"))
    result = save(ns, engine, data)
    assert result["purchase"] == {"created": 0, "updated": 1, "linesCreated": 0, "linesUpdated": 2}
    assert declaration(engine)["content_sha256"] == first
    assert len(rows(engine, "SELECT id FROM source_raw_records")) == raw_count


def test_changed_amount_changes_digest_and_appends_raw_record(ns, engine):
    save(ns, engine, bundle([purchase()], [customs()]))
    first = declaration(engine)["content_sha256"]
    raw_count = len(rows(engine, "SELECT id FROM source_raw_records"))
    save(ns, engine, bundle([purchase(amounts=("101.00", "20.00"))], [customs()]))
    assert declaration(engine)["content_sha256"] != first
    assert len(rows(engine, "SELECT id FROM source_raw_records")) > raw_count


def test_removed_line_is_deactivated_and_its_links_stale(ns, engine):
    save(ns, engine, bundle([purchase()], [customs()]))
    order_id, head, lines = purchase()
    save(ns, engine, bundle([(order_id, head, lines[:1])], [customs()]))
    active = rows(engine, "SELECT source_line_key FROM source_purchase_order_lines WHERE is_active = 1")
    assert len(active) == 1
    with engine.connect() as connection:
        content = snapshot(connection, declaration(engine)["id"])
    assert all(
        link["purchase_line_id"] in {line["id"] for line in content["purchase_lines"]}
        for link in content["links"]
        if link["purchase_line_id"]
    )


def test_missing_amount_marked_source_missing(ns, engine):
    save(ns, engine, bundle([purchase(amounts=("100.50", ""))], [customs()]))
    statuses = sorted(
        r["amount_status"] for r in rows(engine, "SELECT amount_status FROM source_purchase_order_lines")
    )
    assert statuses == ["matched", "source_missing"]


def test_order_moving_to_other_declaration_marks_old_one_dependent(ns, engine):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    old = declaration(engine, "870")
    # 子采购单改挂到报关单 871；本次只同步 871，870 未同步
    save(ns, engine, bundle([purchase(customs_id="871")], [customs("871")]))
    moved = declaration(engine, "870")
    assert moved["relation_status"] == "partial"
    assert DEPENDENCY_ISSUE in json.loads(moved["relation_issues"])  # 原始 SQL 读出的 JSON 为文本
    assert moved["content_sha256"] != old["content_sha256"]
    active_old = rows(
        engine,
        "SELECT * FROM source_customs_purchase_links WHERE customs_declaration_id = :i AND status = 'active'",
        i=old["id"],
    )
    assert active_old == []


def test_partial_evidence_keeps_issues(ns, engine):
    data = bundle([purchase()], [customs()])
    data["relation_evidence"]["870"] = evidence(status="partial")
    save(ns, engine, data)
    head = declaration(engine)
    assert head["relation_status"] == "partial" and head["relation_issues"]


def test_without_evidence_only_header_link_and_partial(ns, engine):
    save(ns, engine, bundle([purchase()], [customs()], with_evidence=False))
    links = rows(engine, "SELECT evidence FROM source_customs_purchase_links WHERE status = 'active'")
    assert [link["evidence"] for link in links] == ["ns_reference"]
    assert declaration(engine)["relation_status"] == "partial"


def test_older_source_version_is_rejected_and_nothing_saved(ns, engine):
    save(ns, engine, bundle([purchase()], [customs(modified="2026-09-03T00:00:00Z")]))
    before = declaration(engine)
    with pytest.raises(ApiError, match="早于已保存版本"):
        save(
            ns,
            engine,
            bundle([purchase(amounts=("1.00", "2.00"))], [customs(modified="2026-09-01T00:00:00Z")]),
        )
    assert declaration(engine)["content_sha256"] == before["content_sha256"]
    amounts = rows(engine, "SELECT amount FROM source_purchase_order_lines ORDER BY source_line_key")
    assert Decimal(str(amounts[0]["amount"])) == Decimal("100.50")  # 整页回滚


def test_missing_configured_field_rejects_page(ns, engine):
    order_id, head, lines = purchase()
    del lines[0][1]["custrecord_swc_subpo_item_bgname"]
    with pytest.raises(ApiError, match="缺少已配置字段"):
        save(ns, engine, bundle([(order_id, head, lines)], [customs()]))
    assert rows(engine, "SELECT id FROM source_purchase_orders") == []


def test_declaration_service_reads_page_detail_and_digest(ns, engine):
    save(ns, engine, bundle([purchase()], [customs()]))
    service = DeclarationService(engine)
    total, page = service.page(ACCOUNT, "PL001", 1, 20)
    assert total == 1 and page[0]["record_no"] == "CD870"
    content = service.detail(page[0]["id"])
    assert len(content["customs_lines"]) == 2 and len(content["purchase_lines"]) == 2
    assert content["orders"][0]["supplier_name"] == "上海 供应商（有限）公司"
    assert digest(content) == page[0]["content_sha256"]
    with pytest.raises(ApiError):
        service.detail(999)
    with service.locked(ACCOUNT) as connection:
        assert snapshot(connection, page[0]["id"])["declaration"]["record_no"] == "CD870"


def test_sync_page_reads_ns_and_relations_then_saves(ns, engine, monkeypatch):
    data = bundle([purchase()], [customs()], with_evidence=False)
    reads = []

    class FakeReader:
        def __init__(self, client):
            assert client is ns

        def collect_records(self, kind, page_rows):
            reads.append((kind, page_rows))
            return deepcopy(data)

    class FakeRelations:
        def __init__(self, client):
            pass

        def collect(self, collected, *, match):
            assert match is True and collected["customs"]
            return {"870": evidence("870")}

    monkeypatch.setattr("backend.modules.source.service.storage_service.PlReader", FakeReader)
    monkeypatch.setattr("backend.modules.source.service.storage_service.RelationReader", FakeRelations)
    # 完整同步要求原始报关行与 v3 关联接口均已配置
    for key in ("finance_source_script", "finance_source_deploy", "pl_restlet_script", "pl_restlet_deploy"):
        setattr(ns.settings, key, "configured")
    page = {"rows": [{"id": "870"}], "page": 1, "hasNext": False}
    result = StorageService(ns, engine).sync_page("customs-declarations", lambda: page)
    assert reads == [("customs-declarations", page["rows"])]
    assert result["storage"]["relations"]["matched"] == 1
    assert result["message"] == result["storage"]["message"] and result["page"] == 1
    assert declaration(engine)["relation_status"] == "complete"


def test_sync_page_rejects_unsupported_kind(ns, engine):
    with pytest.raises(ApiError, match="标准采购订单"):
        StorageService(ns, engine).sync_page("purchase-orders", lambda: {"rows": []})
