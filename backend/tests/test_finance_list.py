"""本地自动列表：真实 SQL 查询验证隔离、完整单据分页及不猜配/不冒充已报关金额。"""

import hashlib
from decimal import Decimal

import pytest
from backend.app import create_app
from backend.modules.business import relation_dao
from backend.modules.business.entity import load_tables
from backend.modules.business.public import CustomsReconciliationSource
from backend.modules.business.relation_entity import RELATION_TABLE, define_relation_table
from backend.modules.business.relation_storage_mapper import relation_values
from backend.modules.reconciliation.dto import ApproveRequest, DeclarationListQuery
from backend.modules.reconciliation.local_mapper import declarations
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.source.dto.pl_comparison import PlScriptQuery
from backend.modules.source.policy.relation_policy import incomplete_reason, source_digest
from backend.modules.source.service.pl_comparison_service import PlScriptService
from backend.tests.test_api import login
from backend.tests.test_reconciliation import review_context as review_context
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine, select

OWNER = "user:admin"


@pytest.fixture
def local_source(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'business.sqlite'}")
    metadata = MetaData()
    definitions = {
        "customs_declarations": "tenant_id ns_account ns_internal_id record_no declaration_no declaration_date declarant_name detail_sync_status source_data",
        "customs_declaration_lines": "tenant_id pl_no declaration_name specification quantity unit_name declared_quantity declared_unit unit_price amount currency_code company_name",
        "purchase_orders": "tenant_id ns_account order_no parent_order_no pl_no supplier_identifier supplier_name company_identifier company_name currency_code detail_sync_status source_data",
        "purchase_order_lines": "tenant_id item_name declaration_name specification quantity unit_name tax_inclusive_price amount",
    }
    foreign = {
        "customs_declaration_lines": "customs_declaration_id",
        "purchase_orders": "customs_declaration_id",
        "purchase_order_lines": "purchase_order_id",
    }
    tables = {}
    for name, fields in definitions.items():
        columns = [Column("id", Integer, primary_key=True), Column("is_active", Integer, default=1)]
        columns += [Column(field, JSON if field == "source_data" else String) for field in fields.split()]
        if name in foreign:
            columns.append(Column(foreign[name], Integer))
        if name.endswith("_lines"):
            columns.append(Column("line_no", Integer, default=1))
        tables[name] = Table(name, metadata, *columns)
    define_relation_table(metadata)
    metadata.create_all(engine)
    tenant = hashlib.sha256(OWNER.encode()).hexdigest()
    with engine.begin() as c:
        for identity, account, owner, active in [
            (1, "prod", tenant, 1),
            (2, "sb", tenant, 1),
            (3, "prod", "other", 1),
            (4, "prod", tenant, 0),
            (5, "prod", tenant, 1),
        ]:
            c.execute(
                tables["customs_declarations"]
                .insert()
                .values(
                    id=identity,
                    tenant_id=owner,
                    ns_account=account,
                    ns_internal_id="same-ns-id" if identity < 4 else f"other-ns-id-{identity}",
                    record_no=f"CD00{identity}",
                    declaration_no=f"REAL{identity}",
                    declaration_date="2026-09-01",
                    declarant_name="公司",
                    detail_sync_status="complete",
                    is_active=active,
                    source_data={"secret": "raw"},
                )
            )
        c.execute(
            tables["customs_declaration_lines"]
            .insert()
            .values(
                id=1,
                tenant_id=tenant,
                customs_declaration_id=1,
                pl_no="PL-SAME",
                declaration_name="杯子",
                quantity="20",
                unit_name="包",
                declared_quantity="8.5",
                declared_unit="千克",
                amount="50",
                company_name="申报主体",
            )
        )
        # 相同 PL、品名和 NS ID 不可跨账套连到同一个本地单头。
        for identity, account, owner, parent, active in [
            (1, "prod", tenant, 1, 1),
            (2, "sb", tenant, 1, 1),
            (3, "prod", "other", 1, 1),
            (4, "prod", tenant, 1, 0),
            (5, "prod", tenant, None, 1),
        ]:
            c.execute(
                tables["purchase_orders"]
                .insert()
                .values(
                    id=identity,
                    tenant_id=owner,
                    ns_account=account,
                    customs_declaration_id=parent,
                    order_no=f"SUB{identity}",
                    parent_order_no="PO1",
                    pl_no="PL-SAME",
                    supplier_name="供应商",
                    currency_code="CNY",
                    detail_sync_status="complete",
                    is_active=active,
                )
            )
            c.execute(
                tables["purchase_order_lines"]
                .insert()
                .values(
                    id=identity,
                    tenant_id=owner,
                    purchase_order_id=identity,
                    declaration_name="杯子",
                    quantity="100.0000",
                    amount="9007199254740993.01",
                    unit_name=None,
                    tax_inclusive_price="2.00",
                )
            )
        c.execute(
            tables["purchase_order_lines"]
            .insert()
            .values(
                id=6,
                tenant_id=tenant,
                purchase_order_id=1,
                declaration_name="第二商品",
                quantity="5",
                amount="10",
                unit_name="个",
            )
        )
        c.execute(
            tables["purchase_order_lines"]
            .insert()
            .values(id=7, tenant_id="other", purchase_order_id=1, declaration_name="越权明细")
        )
        c.execute(
            tables["purchase_order_lines"]
            .insert()
            .values(id=8, tenant_id=tenant, purchase_order_id=1, declaration_name="停用明细", is_active=0)
        )
    yield CustomsReconciliationSource(engine)
    engine.dispose()


def read(source, owner=OWNER, **kwargs):
    return source.read(
        owner, **{"keyword": "", "account": "", "page": 1, "page_size": 20, "include_rows": True, **kwargs}
    )


def test_scope_direct_fk_and_no_partial_order_as_declared(local_source):
    data = read(local_source)
    assert data["total"] == 3
    assert data["accounts"] == ["prod", "sb"]
    assert [row["id"] for row in data["purchases"]] == [1]
    assert [row["id"] for row in data["lines"]] == [1, 6]
    assert all("source_data" not in head for head in data["heads"])
    group = next(group for group in declarations(data) if group.recordNumber == "CD001")
    assert group.purchaseCount == 2
    assert group.customsLines[0].quantity == "8.5"
    assert group.customsLines[0].unit == "千克"
    assert group.company == "申报主体"
    assert group.customsLines[0].purchaseLines == []
    assert not group.review.allowed and group.snapshotId == ""
    purchase = group.unlinkedLines[0]
    assert purchase.scope == "order" and purchase.quantity == "100.0000"
    assert purchase.amount == "9007199254740993.01" and purchase.unit == ""
    assert read(local_source, owner="user:invisible")["total"] == 0


def test_child_purchase_report_quantity_and_unit_are_displayed_as_a_pair(local_source):
    data = read(local_source, keyword="CD001")
    data["lines"] = [
        dict(row, declaration_quantity="8.5", declaration_unit="千克") if row["id"] == 1 else row
        for row in data["lines"]
    ]
    purchase = declarations(data)[0].unlinkedLines[0]
    assert (purchase.quantity, purchase.unit) == ("8.5", "千克")
    assert "子采购报关数量和单位" in purchase.note

    # 只得到单位而没有同口径数量时，不能把原始数量与报关单位拼在一起。
    data["lines"][0]["declaration_quantity"] = None
    purchase = declarations(data)[0].unlinkedLines[0]
    assert (purchase.quantity, purchase.unit) == ("100.0000", "")


@pytest.mark.parametrize("keyword", ["cd001", "REAL1", "pl-same", "SUB1", "杯子", "第二商品", "申报主体"])
def test_search_returns_whole_declaration_with_all_lines(local_source, keyword):
    data = read(local_source, keyword=keyword)
    assert data["total"] == 1
    assert len(data["lines"]) == 2
    assert data["heads"][0]["record_no"] == "CD001"


@pytest.mark.parametrize("keyword", ["SUB2", "SUB3", "SUB4", "SUB5", "越权明细", "停用明细", "%", "_"])
def test_no_cross_account_or_inactive_search_leak_and_wildcards_are_literal(local_source, keyword):
    assert read(local_source, keyword=keyword)["total"] == 0


def test_pagination_accounts_counts_and_read_only_browse(local_source, context):
    assert read(local_source, account="sb")["total"] == 1
    first = read(local_source, page_size=1)
    second = read(local_source, page_size=1, page=2)
    assert first["total"] == second["total"] == 3
    assert first["heads"][0]["id"] != second["heads"][0]["id"]
    assert not read(local_source, page=100)["heads"]
    service = ReconciliationService(context.settings, None, context.engine, local_source)
    result = service.browse(DeclarationListQuery(status="approved"), OWNER)
    assert result.counts["all"] == result.counts["pending"] == 3
    assert result.counts["blocked"] == 0
    assert result.groups == [] and result.total == 0
    assert result.source == "database"
    result = service.browse(DeclarationListQuery(pageSize=2), OWNER)
    assert result.pages == 2 and result.counts["shown"] == 2


def test_decimal_remains_exact(local_source):
    data = read(local_source, keyword="CD001")
    data["lines"] = [dict(data["lines"][0], amount=Decimal("9007199254740993.0100"))]
    assert declarations(data)[0].unlinkedLines[0].amount == "9007199254740993.01"


def test_list_api_auth_validation_and_auto_load_without_ns(context, local_source):
    with TestClient(create_app(context.settings, context.ns, context.engine, local_source.engine)) as client:
        path = "/api/reconciliation/declarations"
        assert client.post(path, json={}).status_code == 401
        login(client, context)
        assert client.post(path, json={}).status_code == 403
        client.headers.update({"Origin": context.settings.origin})
        assert client.post(path, json={"owner": "other"}).status_code == 400
        assert client.post(path, json={"pageSize": 1000}).status_code == 400
        assert client.post(path, json={"page": 0}).status_code == 400
        response = client.post(path, json={})
        assert response.status_code == 200
        assert response.json()["counts"]["all"] == 3
        assert not context.ns.writes


def save_comparison(local_source, context):
    context.settings.account = context.data["account"] = "prod"
    context.data["groups"][0]["recordNumber"] = "CD001"
    raw = (
        PlScriptService(context.ns)
        .query(PlScriptQuery(type="customsRecord", pl="CD001"))
        .groups[0]
        .model_dump()
    )
    context.calls.clear()
    payload = {"version": 3, "group": raw}
    reason = incomplete_reason(raw, 3)
    evidence = {
        "version": 1,
        "account": "prod",
        "declarationId": "101",
        "status": "partial" if reason else "matched",
        "rawLines": [],
        "packingLines": [],
        "issues": [],
        "comparison": {
            "payload": payload,
            "digest": source_digest(payload),
            "ready": not reason,
            "reason": reason,
        },
    }
    with local_source.engine.begin() as connection:
        tables = load_tables(connection, include_relations=True)
        table = tables["customs_declarations"]
        connection.execute(
            table.update()
            .where(table.c.id == 1)
            .values(
                ns_internal_id="101",
            )
        )
        head = connection.execute(select(table).where(table.c.id == 1)).mappings().one()
        relation_dao.save_result(connection, tables[RELATION_TABLE], relation_values(head, evidence))


def test_saved_relations_auto_display_filter_and_approval_rechecks_local_content(
    local_source, review_context
):
    context = review_context
    save_comparison(local_source, context)
    service = ReconciliationService(context.settings, context.service.source, context.engine, local_source)
    result = service.browse(DeclarationListQuery(keyword="CD001", status="pending", pageSize=1), OWNER)
    assert result.total == result.counts["pending"] == 1
    assert result.counts["all"] == 1 and result.counts["blocked"] == 0
    group = result.groups[0]
    assert group.review.allowed and group.snapshotId
    assert not group.unlinkedLines and group.customsLines[0].purchaseLines[0].amount == "125.00"
    assert context.calls == []  # 展示只读数据库，不在每次打开页面时重新拉取NS。
    approved = service.approve(ApproveRequest(snapshotId=group.snapshotId, note="隔离测试"), OWNER)
    assert approved.review.status == "approved" and context.calls == []
    result = service.browse(DeclarationListQuery(status="approved"), OWNER)
    assert result.total == 1 and result.groups[0].review.status == "approved"
    assert service.browse(DeclarationListQuery(keyword="CD001", status="pending"), OWNER).total == 0
    context.data["groups"][0]["rows"][1]["cells"][14] = "126.00"
    save_comparison(local_source, context)
    changed = service.browse(DeclarationListQuery(keyword="CD001", status="pending"), OWNER)
    assert changed.total == 1 and changed.counts["approved"] == 0
    assert changed.groups[0].customsLines[0].purchaseLines[0].amount == "126.00"


def test_saved_partial_relations_wait_for_finance_without_extra_machine_gate(local_source, review_context):
    context = review_context
    context.data["groups"][0]["rows"][1]["customsRowId"] = None
    save_comparison(local_source, context)
    service = ReconciliationService(context.settings, context.service.source, context.engine, local_source)
    result = service.browse(DeclarationListQuery(keyword="CD001", status="pending"), OWNER)
    assert result.total == 1 and result.counts["pending"] == 1
    assert len(result.groups[0].unlinkedLines) == 1 and result.groups[0].review.allowed
    assert result.groups[0].review.label == "待审核"


def test_local_review_keeps_stored_account_independent_of_live_ns_connection(local_source, review_context):
    context = review_context
    save_comparison(local_source, context)
    context.settings.account = "sandbox"
    service = ReconciliationService(context.settings, context.service.source, context.engine, local_source)
    group = service.browse(DeclarationListQuery(keyword="CD001", status="pending"), OWNER).groups[0]
    assert group.review.status == "pending" and group.review.allowed and group.snapshotId
    approved = service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER)
    assert approved.account == "prod" and approved.review.status == "approved"
    assert not context.calls
