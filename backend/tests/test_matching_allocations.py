"""匹配规则及专用MySQL事务验证；不使用真实发票或业务库。"""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.modules.business.public import PurchaseMatchingSource
from backend.modules.invoice.service import InvoiceService
from backend.modules.matching.dto import ConfirmRequest, LinkPair, LinkRequest
from backend.modules.matching.entity import allocations
from backend.modules.matching.entity import metadata as matching_metadata
from backend.modules.matching.policy import remark_matches
from backend.modules.matching.service import MatchingService
from backend.tests.test_business_migrations import migrated_engine  # noqa: F401
from sqlalchemy import MetaData, Table, create_engine, func, select


def sample():
    invoice = {
        "id": "1",
        "seller": "工厂A",
        "buyer": "公司A",
        "currency": "CNY",
        "sourceStatus": "normal",
        "sourceComplete": True,
        "remark": "订单 PO100",
        "gross": "60",
        "lines": [{"id": "11", "item": "*金属制品*杯子", "quantity": "6", "unit": "个", "gross": "60"}],
    }
    heads = [
        {
            "id": 1,
            "supplier_name": "工厂A",
            "company_name": "公司A",
            "order_no": "CH1",
            "parent_order_no": "PO100",
            "verified_parent_order_no": "PO100",
            "currency_code": "CNY",
            "detail_sync_status": "complete",
        }
    ]
    lines = [
        {
            "id": 21,
            "purchase_order_id": 1,
            "item_name": "杯子",
            "declaration_name": "杯子",
            "quantity": D("10"),
            "unit_name": "个",
            "declaration_quantity": D("10"),
            "declaration_unit": "个",
            "tax_inclusive_price": D("10"),
            "amount": D("100"),
        }
    ]
    return invoice, heads, lines


def test_partial_quantity_and_parent_remark_are_candidates():
    view = MatchingService(None, None).evaluate(*sample(), [])
    row = view["candidates"][0]
    assert row["allowed"] and not row["allFieldsMatched"]
    assert view["linkAllowed"]
    assert row["suggestedQuantity"] == "6"
    assert row["basis"] == "备注采购订单命中"
    assert row["checks"][2]["difference"] == "-4"


def test_remark_requires_complete_identifier():
    assert remark_matches("采购订单：ＰＯ１００，附件", "PO100")
    assert not remark_matches("PO1001", "PO100")
    assert not remark_matches("X-PO100", "PO100")


@pytest.mark.parametrize(
    "field,value",
    [
        ("buyer", None),
        ("currency", None),
        ("currency", "USD"),
        ("sourceStatus", "red_offset"),
        ("sourceComplete", False),
    ],
)
def test_missing_identity_currency_or_red_status_blocks(field, value):
    invoice, heads, lines = sample()
    invoice[field] = value
    row = MatchingService(None, None).evaluate(invoice, heads, lines, [])["candidates"][0]
    assert not row["allowed"] and row["reason"]
    if field in {"sourceStatus", "sourceComplete"}:
        assert not MatchingService(None, None).evaluate(invoice, heads, lines, [])["linkAllowed"]


def test_wrong_supplier_on_remark_is_visible_but_blocked():
    invoice, heads, lines = sample()
    heads[0]["supplier_name"] = "其他工厂"
    view = MatchingService(None, None).evaluate(invoice, heads, lines, [])
    assert len(view["candidates"]) == 1 and not view["candidates"][0]["allowed"]


def test_multiple_candidates_are_preserved():
    invoice, heads, lines = sample()
    lines.append({**lines[0], "id": 22})
    assert MatchingService(None, None).evaluate(invoice, heads, lines, [])["candidateCount"] == 2


def test_one_invoice_links_two_child_orders_without_manual_allocation():
    invoice, heads, lines = sample()
    lines[0]["declaration_quantity"] = D("3")
    lines[0]["amount"] = D("30")
    heads.append({**heads[0], "id": 2, "order_no": "CH2"})
    lines.append({**lines[0], "id": 22, "purchase_order_id": 2})
    service = MatchingService(None, None)
    view = service.evaluate(invoice, heads, lines, [])
    pairs = [
        LinkPair(invoiceLineId="11", purchaseLineId="21"),
        LinkPair(invoiceLineId="11", purchaseLineId="22"),
    ]
    assert len(service.validate_links(invoice, heads, lines, [], [], view, pairs)) == 2
    with pytest.raises(ApiError, match="汇总不一致"):
        service.validate_links(invoice, heads, lines, [], [], view, pairs[:1])
    with pytest.raises(ApiError, match="重复选择"):
        service.validate_links(invoice, heads, lines, [], [], view, pairs * 2)
    with pytest.raises(ApiError, match="已有整票关联"):
        service.validate_links(
            invoice,
            heads,
            lines,
            [],
            [{"invoice_id": "2", "purchase_line_id": "21"}],
            view,
            pairs,
        )
    heads[1]["supplier_name"] = "其他供应商"
    with pytest.raises(ApiError, match="供应商主体待核实"):
        service.validate_links(invoice, heads, lines, [], [], view, pairs)


def test_whole_invoice_link_persists_atomically_without_allocation(monkeypatch):
    invoice, heads, lines = sample()
    lines[0]["declaration_quantity"] = D("3")
    lines[0]["amount"] = D("30")
    heads.append({**heads[0], "id": 2, "order_no": "CH2"})
    lines.append({**lines[0], "id": 22, "purchase_order_id": 2})
    engine = create_engine("sqlite:///:memory:")
    matching_metadata.create_all(engine)

    class MysqlContract:
        dialect = SimpleNamespace(name="mysql")

        def begin(self):
            return engine.begin()

        def connect(self):
            return engine.connect()

    invoices = Mock()
    invoices.invoice_detail.return_value = invoice
    purchases = Mock()
    purchases.read.return_value = (heads, lines)
    monkeypatch.setattr("backend.modules.matching.service.matching_invoice", lambda *_: invoice)
    service = MatchingService(invoices, purchases, MysqlContract())
    owner = "isolated-link-test"
    view = service.preview(1, owner)
    body = LinkRequest(
        requestId=uuid4(),
        snapshot=view["snapshot"],
        pairs=[
            LinkPair(invoiceLineId=row["invoiceLineId"], purchaseLineId=row["purchaseLineId"])
            for row in view["candidates"]
        ],
    )
    assert service.link(1, body, owner)["linkedLines"] == 2
    assert service.link(1, body, owner)["linkedLines"] == 2
    refreshed = service.preview(1, owner)
    assert len(refreshed["links"]) == 2
    assert all(not row["allowed"] for row in refreshed["candidates"])
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(allocations)) == 0
    with pytest.raises(ApiError, match="发生变化"):
        service.link(1, body.model_copy(update={"requestId": uuid4()}), owner)
    lines[0]["amount"] = D("31")
    assert any(row["needsReview"] for row in service.preview(1, owner)["links"])
    engine.dispose()


def test_invoice_uses_child_declaration_units_and_purchase_amounts():
    invoice = {
        "id": "28",
        "seller": "义乌市尚图数码影像有限公司",
        "buyer": "上海绎色数码科技有限公司",
        "currency": "CNY",
        "sourceStatus": "unknown",
        "sourceComplete": True,
        "remark": "请购单号：YEX251208-01；订单编号：YE-ST251231-Y593",
        "lines": [
            {"id": "1", "item": "*其他机械设备*胸章机", "quantity": "10", "unit": "台", "gross": "913"},
            {"id": "2", "item": "*金属制品*胸章", "quantity": "2000", "unit": "套", "gross": "1560"},
        ],
    }
    heads = [
        {
            "id": 201,
            "order_no": "YE-ST251231-Y593-1",
            "parent_order_no": "YE-ST251231-Y593",
            "verified_parent_order_no": "YE-ST251231-Y593",
            "supplier_name": "浙江义乌市尚图数码影像有限公司",
            "company_name": invoice["buyer"],
            "currency_code": None,
            "parent_currency_code": "人民币",
            "detail_sync_status": "complete",
            "customs_record_no": "CD000252",
            "customs_declaration_no": "310120260519278380",
        }
    ]
    lines = [
        {
            "id": 301,
            "purchase_order_id": 201,
            "item_name": "胸章机套装",
            "declaration_name": "胸章机",
            "quantity": D("10"),
            "unit_name": "套",
            "declaration_quantity": D("10"),
            "declaration_unit": "台",
            "amount": D("913"),
        },
        {
            "id": 302,
            "purchase_order_id": 201,
            "item_name": "胸章机耗材",
            "declaration_name": "胸章",
            "quantity": D("2000"),
            "unit_name": None,
            "declaration_quantity": D("2000"),
            "declaration_unit": "套",
            "amount": D("1560"),
        },
    ]
    view = MatchingService(None, None).evaluate(invoice, heads, lines, [])
    candidates = view["candidates"]
    assert view["candidateCount"] == 2 and view["highConfidenceCount"] == 0
    assert all(row["matchStatus"] == "匹配不一致，需人工核实" for row in candidates)
    assert all(not row["allowed"] and "供应商主体待核实" in row["reason"] for row in candidates)
    assert all("销售方与供应商不一致" in row["warnings"][0] for row in candidates)
    assert {row["unit"] for row in candidates} == {"台", "套"}
    invoice["remark"] = "报关单号：310120260519278380"
    assert all(
        row["basis"] == "备注报关单命中"
        for row in MatchingService(None, None).evaluate(invoice, heads, lines, [])["candidates"]
    )
    invoice["remark"] = "无订单线索"
    manual = MatchingService(None, None).evaluate(invoice, heads, lines, [], customs_no="CD000252")
    assert manual["candidateCount"] == 2
    assert all(row["basis"] == "备注报关单命中" for row in manual["candidates"])
    assert manual["snapshot"] != MatchingService(None, None).evaluate(invoice, heads, lines, [])["snapshot"]
    invoice["remark"] = "订单编号：YE-ST251231-Y593"
    conflict = MatchingService(None, None).evaluate(invoice, heads, lines, [], customs_no="CD000999")
    assert conflict["highConfidenceCount"] == 0
    assert all(
        not row["allowed"] and row["matchStatus"] == "报关线索冲突，待核实" for row in conflict["candidates"]
    )


def test_prior_allocation_limits_remaining_and_source_change_blocks():
    invoice, heads, lines = sample()
    service = MatchingService(None, None)
    candidate = service.evaluate(invoice, heads, lines, [])["candidates"][0]
    allocation = {
        "invoice_id": "1",
        "invoice_line_id": "11",
        "purchase_line_id": "21",
        "quantity": D("4"),
        "gross": D("40"),
        "source_hash": candidate["sourceHash"],
        "purchase_hash": candidate["purchaseHash"],
    }
    view = service.evaluate(invoice, heads, lines, [allocation])
    assert view["candidates"][0]["suggestedQuantity"] == "2"
    lines[0]["synced_at"] = "new-sync-time"
    assert not service.evaluate(invoice, heads, lines, [allocation])["allocations"][0]["needsReview"]
    lines[0]["quantity"] = D("8")
    lines[0]["amount"] = D("80")
    view = service.evaluate(invoice, heads, lines, [allocation])
    assert view["allocations"][0]["needsReview"]
    assert not view["candidates"][0]["allowed"]


@pytest.fixture
def matching_db(request):
    engine = request.getfixturevalue("migrated_engine")
    owner = "matching-test:" + uuid4().hex
    tenant = hashlib.sha256(owner.encode()).hexdigest()
    metadata = MetaData()
    tables = {
        name: Table(name, metadata, autoload_with=engine)
        for name in ("invoices", "invoice_lines", "purchase_orders", "purchase_order_lines")
    }
    ids = []
    with engine.begin() as connection:
        for _ in range(2):
            invoice_id = connection.execute(
                tables["invoices"]
                .insert()
                .values(
                    tenant_id=tenant,
                    external_system="test",
                    external_account="test",
                    external_record_id=uuid4().hex,
                    source_data={},
                    invoice_no=uuid4().hex[:20],
                    invoice_direction="input",
                    seller_name="工厂A",
                    buyer_name="公司A",
                    currency_code="CNY",
                    invoice_status="normal",
                    detail_sync_status="complete",
                    amount_including_tax=D("60"),
                )
            ).inserted_primary_key[0]
            connection.execute(
                tables["invoice_lines"]
                .insert()
                .values(
                    tenant_id=tenant,
                    invoice_id=invoice_id,
                    source_line_key="1",
                    item_name="杯子",
                    unit_name="个",
                    quantity=D("6"),
                    amount_including_tax=D("60"),
                )
            )
            ids.append(invoice_id)
        purchase_id = connection.execute(
            tables["purchase_orders"]
            .insert()
            .values(
                tenant_id=tenant,
                ns_account="test",
                ns_internal_id=uuid4().hex,
                source_data={},
                order_no="CH1",
                supplier_name="工厂A",
                company_name="公司A",
                currency_code="CNY",
                detail_sync_status="complete",
            )
        ).inserted_primary_key[0]
        connection.execute(
            tables["purchase_order_lines"]
            .insert()
            .values(
                tenant_id=tenant,
                purchase_order_id=purchase_id,
                source_line_key="1",
                item_name="杯子",
                declaration_name="杯子",
                unit_name="个",
                quantity=D("10"),
                declaration_quantity=D("10"),
                declaration_unit="个",
                tax_inclusive_price=D("10"),
                amount=D("100"),
            )
        )
    yield MatchingService(InvoiceService(engine), PurchaseMatchingSource(engine), engine), owner, ids


def request(view, quantity="6", **overrides):
    candidate = view["candidates"][0]
    return ConfirmRequest(
        **{
            "requestId": str(uuid4()),
            "snapshot": view["snapshot"],
            "invoiceLineId": candidate["invoiceLineId"],
            "purchaseLineId": candidate["purchaseLineId"],
            "quantity": quantity,
            **overrides,
        }
    )


def test_mysql_confirm_idempotency_reload_and_stale_snapshot(matching_db):
    service, owner, ids = matching_db
    view = service.preview(ids[0], owner)
    body = request(view, "4")
    assert service.confirm(ids[0], body, owner)["gross"] == "40.00000000"
    assert "已经保存" in service.confirm(ids[0], body, owner)["message"]
    refreshed = service.preview(ids[0], owner)
    assert len(refreshed["allocations"]) == 1
    assert D(refreshed["candidates"][0]["invoiceRemaining"]) == 2
    with pytest.raises(ApiError, match="发生变化"):
        service.confirm(ids[0], request(view, "2"), owner)
    with pytest.raises(ApiError, match="其他分配"):
        service.confirm(ids[0], body.model_copy(update={"quantity": "1"}), owner)


def test_mysql_overallocation_scope_and_rollback(matching_db):
    service, owner, ids = matching_db
    view = service.preview(ids[0], owner)
    with pytest.raises(ApiError, match="剩余数量"):
        service.confirm(ids[0], request(view, "7"), owner)
    assert service.preview(ids[0], owner)["allocations"] == []
    with pytest.raises(ApiError, match="无权"):
        service.confirm(ids[0], request(view), "another-owner")


def test_mysql_concurrent_invoices_cannot_overallocate(matching_db):
    service, owner, ids = matching_db
    bodies = [request(service.preview(i, owner)) for i in ids]

    def run(index):
        try:
            service.confirm(ids[index], bodies[index], owner)
            return "saved"
        except ApiError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results.count("saved") == 1
    with service.engine.connect() as connection:
        total = connection.scalar(
            select(func.sum(allocations.c.quantity)).where(
                allocations.c.tenant_id == hashlib.sha256(owner.encode()).hexdigest()
            )
        )
    assert total == D("6")


def test_mysql_partial_allocation_across_invoices(matching_db):
    service, owner, ids = matching_db
    service.confirm(ids[0], request(service.preview(ids[0], owner)), owner)
    view = service.preview(ids[1], owner)
    assert D(view["candidates"][0]["suggestedQuantity"]) == 4
    service.confirm(ids[1], request(view, "4"), owner)
    assert not service.preview(ids[1], owner)["candidates"][0]["allowed"]


def test_mysql_whole_invoice_links_multiple_orders(matching_db):
    service, owner, ids = matching_db
    tenant = hashlib.sha256(owner.encode()).hexdigest()
    metadata = MetaData()
    heads = Table("purchase_orders", metadata, autoload_with=service.engine)
    lines = Table("purchase_order_lines", metadata, autoload_with=service.engine)
    first = service.preview(ids[0], owner)["candidates"][0]
    with service.engine.begin() as connection:
        connection.execute(
            lines.update()
            .where(lines.c.id == int(first["purchaseLineId"]))
            .values(declaration_quantity=D("3"), amount=D("30"))
        )
        order_id = connection.execute(
            heads.insert().values(
                tenant_id=tenant,
                ns_account="test",
                ns_internal_id=uuid4().hex,
                source_data={},
                order_no="CH2",
                supplier_name="工厂A",
                company_name="公司A",
                currency_code="CNY",
                detail_sync_status="complete",
            )
        ).inserted_primary_key[0]
        connection.execute(
            lines.insert().values(
                tenant_id=tenant,
                purchase_order_id=order_id,
                source_line_key="1",
                item_name="杯子",
                declaration_name="杯子",
                unit_name="个",
                quantity=D("3"),
                declaration_quantity=D("3"),
                declaration_unit="个",
                amount=D("30"),
            )
        )
    view = service.preview(ids[0], owner)
    assert {row["orderNo"] for row in view["candidates"]} == {"CH1", "CH2"}
    body = LinkRequest(
        requestId=uuid4(),
        snapshot=view["snapshot"],
        pairs=[
            LinkPair(invoiceLineId=row["invoiceLineId"], purchaseLineId=row["purchaseLineId"])
            for row in view["candidates"]
        ],
    )
    assert service.link(ids[0], body, owner)["linkedLines"] == 2
    assert "已经保存" in service.link(ids[0], body, owner)["message"]
    refreshed = service.preview(ids[0], owner)
    assert len(refreshed["links"]) == 2
    assert all(not row["needsReview"] for row in refreshed["links"])
    with pytest.raises(ApiError, match="发生变化"):
        service.link(ids[0], body.model_copy(update={"requestId": uuid4()}), owner)
    with pytest.raises(ApiError, match="子采购明细已有"):
        second = service.preview(ids[1], owner)
        service.link(
            ids[1],
            LinkRequest(
                requestId=uuid4(),
                snapshot=second["snapshot"],
                pairs=[
                    LinkPair(invoiceLineId=row["invoiceLineId"], purchaseLineId=row["purchaseLineId"])
                    for row in second["candidates"]
                ],
            ),
            owner,
        )
    with service.engine.begin() as connection:
        connection.execute(
            lines.update().where(lines.c.id == int(first["purchaseLineId"])).values(amount=D("31"))
        )
    assert any(row["needsReview"] for row in service.preview(ids[0], owner)["links"])


def test_mysql_source_change_and_database_failure(matching_db, monkeypatch):
    from backend.modules.matching import dao
    from sqlalchemy.exc import OperationalError

    service, owner, ids = matching_db
    view = service.preview(ids[0], owner)
    original = dao.insert

    def fail_after_insert(connection, values):
        original(connection, values)
        raise OperationalError("test", {}, Exception("test rollback"))

    monkeypatch.setattr(dao, "insert", fail_after_insert)
    with pytest.raises(ApiError, match="结果不明"):
        service.confirm(ids[0], request(view, "2"), owner)
    assert service.preview(ids[0], owner)["allocations"] == []
    monkeypatch.setattr(dao, "insert", original)
    service.confirm(ids[0], request(view, "2"), owner)
    table = Table("purchase_order_lines", MetaData(), autoload_with=service.engine)
    with service.engine.begin() as connection:
        connection.execute(
            table.update()
            .where(table.c.id == int(view["candidates"][0]["purchaseLineId"]))
            .values(quantity=D("9"), amount=D("90"))
        )
    assert service.preview(ids[0], owner)["allocations"][0]["needsReview"]
    assert not service.preview(ids[1], owner)["candidates"][0]["allowed"]


def test_mysql_http_contract_and_authorization(matching_db):
    from backend.core.dependencies import current_owner
    from backend.core.middleware import register_error_handlers
    from backend.modules.matching.controller import create_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service, owner, ids = matching_db
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_router(service))

    def denied():
        raise ApiError(401, "请先登录")

    app.dependency_overrides[current_owner] = denied
    with TestClient(app) as client:
        path = f"/api/matching/invoices/{ids[0]}"
        assert client.get(path).status_code == 401
        app.dependency_overrides[current_owner] = lambda: owner
        view = client.get(path).json()
        body = request(view, "2").model_dump(mode="json")
        for changes in (
            {"quantity": 2},
            {"quantity": "-1"},
            {"quantity": "NaN"},
            {"gross": "1"},
            {"owner": "other"},
        ):
            assert client.post(path + "/confirm", json={**body, **changes}).status_code == 400
        response = client.post(path + "/confirm", json=body)
        assert response.status_code == 200 and D(response.json()["gross"]) == 20
        assert len(client.get(path).json()["allocations"]) == 1
