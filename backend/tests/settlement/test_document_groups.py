"""资料组：共用提单、跨抬头同号合同隔离、旧资料归组、数据换版与并发独占。"""

import io
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.core.middleware import register_error_handlers
from backend.manage import SCHEMA_INI, _config
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.controller.document_controller import create_router
from backend.modules.settlement.controller.document_group_controller import create_router as group_router
from backend.modules.settlement.dao.document_scope import DocumentGroupRef
from backend.modules.settlement.dto.bill_dto import UpdateBillRequest
from backend.modules.settlement.dto.direct_document_dto import DirectDocumentQuery
from backend.modules.settlement.dto.document_group_dto import CreateDocumentGroup, DocumentGroupQuery
from backend.modules.settlement.dto.ledger_dto import LedgerQuery
from backend.modules.settlement.dto.overview_dto import OverviewQuery
from backend.modules.settlement.entity.batch import settlement_batches
from backend.modules.settlement.service.declaration_detail_service import DeclarationDetailService
from backend.modules.settlement.service.document_group_service import DocumentGroupService
from backend.modules.settlement.service.document_group_source import DocumentGroupSource
from backend.modules.settlement.service.document_service import DocumentService
from backend.modules.settlement.service.ledger_service import LedgerService
from backend.modules.settlement.service.overview_service import OverviewService
from backend.modules.settlement.service.receivable_service import ReceivableService
from backend.tests.settlement.documents_support import SELLER, bill_pdf, encoded
from backend.tests.settlement.test_direct_documents import direct_documents
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_batches import services
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select


def create_body(numbers):
    return CreateDocumentGroup(requestId=str(uuid.uuid4()), declarationNos=numbers)


def group_docs(engine, root):
    docs = direct_documents(engine, root)
    candidates, _ = services(engine)
    docs.groups = DocumentGroupService(engine, candidates, docs.reader)
    docs.single_views = docs.views
    docs.views = DocumentService(engine, docs.reader, DocumentGroupSource(candidates))
    docs.bills.documents = docs.views
    docs.contracts.documents = docs.views
    docs.packages.documents = docs.views
    return docs


def make_direct(engine, ns):
    # 870、871 同卖方，872 另一卖方；三张回执有同一个出口合同号。
    second = customs("872", modified="2026-11-20T01:00:00Z")
    second[1]["custrecord_swc_piname"] = {"id": "9", "refName": "另一申报主体"}
    save(ns, engine, bundle([purchase("202", "872")], [second]))
    _import(
        CustomsReceiptService(engine),
        [
            row("REAL870", "01", "墨水", "个", 10, "ACME LTD", total=600),
            row("REAL871", "01", "墨水", "个", 10, "ACME LTD", total=400.5),
            row("REAL872", "01", "墨水", "个", 10, "ACME LTD", total=1000),
        ],
    )


def test_shared_bill_generates_separate_sellers_and_preserves_money(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    single = direct_documents(seeded, tmp_path)
    single.party("ACME LTD", "ACME LTD")
    single.party(SELLER, "EXPORT A")
    seller_b = single.party("另一申报主体", "EXPORT B")
    bill = single.upload("REAL872").bills[0]
    old = single.generate("REAL872", seller_b.id).contracts[0]
    candidates, _ = services(seeded)
    ledger, overview = LedgerService(seeded, candidates), OverviewService(seeded, candidates)
    before = (ledger.query(LedgerQuery()), overview.query(OverviewQuery()))
    with seeded.connect() as conn:
        batch_count = conn.scalar(select(func.count()).select_from(settlement_batches))
    docs = group_docs(seeded, tmp_path)
    body = create_body(["REAL870", "REAL871", "REAL872"])
    group = docs.groups.create(body, "finance-user")
    assert group.amount == "2000.50" and len(group.members) == 3
    assert docs.groups.create(body, "finance-user").id == group.id
    target = DocumentGroupRef(group.id)
    view = docs.views.get(target)
    assert view.bills[0].id == bill.id and view.contracts[0].id == old.id
    assert view.contracts[0].stale and not view.complete
    assert len(view.planned) == 2
    assert {(c.sellerName, c.amount) for c in view.planned} == {
        (SELLER, "1000.50"),
        ("另一申报主体", "1000.00"),
    }
    docs.bills.update(
        target,
        bill.id,
        UpdateBillRequest(
            blNo=bill.blNo,
            portOfLoading=bill.portOfLoading,
            portOfDischarge=bill.portOfDischarge,
            onBoardDate=bill.onBoardDate,
            declarationNos=["REAL870", "REAL871", "REAL872"],
        ),
        "finance-user",
    )
    generated = docs.generate(target, None)
    assert generated.complete and len(generated.contracts) == 2
    assert len({c.key for c in generated.contracts}) == 2
    assert len({c.contractNo for c in generated.contracts}) == 1
    assert all(not c.stale for c in generated.contracts)
    assert all("/direct-document-groups/" in c.fileUrl for c in generated.contracts)
    _, data = docs.packages.build(target)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert len(names) == len(set(names))
    assert len([n for n in names if "/共用提单/" in n]) == 1
    assert len([n for n in names if "销售合同" in n]) == 2
    assert docs.groups.query(DocumentGroupQuery(keyword="另一申报主体")).total == 1
    assert docs.groups.query(DocumentGroupQuery(page=2, pageSize=1)).items == []
    assert docs.groups.query(DocumentGroupQuery(page=2, pageSize=1)).total == 1
    listed = single.list.query(DirectDocumentQuery()).items
    assert all(r.groupId == group.id and not r.createGroup.allowed for r in listed)
    detail = DeclarationDetailService(
        ReceivableService(seeded, candidates, docs.reader), fee_alert=candidates.fee_alert
    ).get("REAL872")
    assert detail.documents.groupId == group.id and detail.documents.scopeKind == "group"
    assert (
        len(detail.documents.contracts) == 1
        and detail.documents.contracts[0].contract.sellerName == "另一申报主体"
    )
    assert (ledger.query(LedgerQuery()), overview.query(OverviewQuery())) == before
    with seeded.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(settlement_batches)) == batch_count
    # 组内某张回执金额换版会让对应合同失效，重新生成沿用同一提单。
    _import(CustomsReceiptService(seeded), [row("REAL872", "01", "墨水", "个", 10, "ACME LTD", total=1200)])
    changed = docs.views.get(target)
    assert any(c.stale for c in changed.contracts) and not changed.package.allowed
    assert docs.generate(target, None).complete
    # 客户换版不能静默生成另一个买方的合同。
    _import(
        CustomsReceiptService(seeded), [row("REAL872", "01", "墨水", "个", 10, "OTHER CUSTOMER", total=1200)]
    )
    blocked = docs.views.get(target)
    assert not blocked.edit.allowed and not blocked.generate.allowed and not blocked.package.allowed
    with pytest.raises(ApiError, match="客户、币种或收汇路径已变化"):
        docs.generate(target, None)


def test_group_validation_and_scoped_http(seeded, ns, tmp_path):
    docs = group_docs(seeded, tmp_path)
    with pytest.raises(ApiError, match="香港中转"):
        docs.groups.create(create_body(["REAL870", "REAL872"]), "finance-user")
    make_direct(seeded, ns)
    _import(
        CustomsReceiptService(seeded), [row("REAL871", "01", "墨水", "个", 10, "OTHER CUSTOMER", total=400.5)]
    )
    with pytest.raises(ApiError, match="同一个境外收货人"):
        docs.groups.create(create_body(["REAL870", "REAL871"]), "finance-user")
    other = row("REAL871", "01", "墨水", "个", 10, "ACME LTD", total=400.5)
    other[14] = "EUR"
    _import(CustomsReceiptService(seeded), [other])
    with pytest.raises(ApiError, match="跨币种"):
        docs.groups.create(create_body(["REAL870", "REAL871"]), "finance-user")
    with pytest.raises(ApiError, match="不能重复"):
        docs.groups.create(create_body(["REAL872", "REAL872"]), "finance-user")
    with pytest.raises(ApiError, match="只读"):
        docs.groups.create(create_body(["REAL872"]), "service:robot")
    with pytest.raises(ApiError, match="有效的 NS"):
        docs.groups.create(create_body(["UNKNOWN"]), "finance-user")
    one = docs.groups.create(create_body(["REAL872"]), "finance-user")
    two = docs.groups.create(create_body(["REAL870"]), "finance-user")
    with pytest.raises(ApiError, match="已在资料组"):
        docs.groups.create(create_body(["REAL872"]), "finance-user")
    with pytest.raises(ApiError, match="已在资料组"):
        docs.single_views.get("REAL872")
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(group_router(docs.groups))
    app.include_router(create_router(docs.views, docs.bills, docs.contracts, docs.packages, groups=True))
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    client = TestClient(app)
    base = f"/api/settlement/direct-document-groups/{one.id}"
    uploaded = client.post(
        base + "/bills", json=dict(fileName="共用提单.pdf", content=encoded(bill_pdf()), declarationNos=[])
    )
    assert uploaded.status_code == 200, uploaded.text
    bill = uploaded.json()["bills"][0]
    assert client.get(bill["fileUrl"]).content.startswith(b"%PDF-")
    assert (
        client.get(f"/api/settlement/direct-document-groups/{two.id}/bills/{bill['id']}/file").status_code
        == 404
    )
    assert (
        client.post(
            f"/api/settlement/direct-document-groups/{two.id}/bills/{bill['id']}/remove", json={}
        ).status_code
        == 404
    )
    assert client.get(base).json()["groupNo"] == one.groupNo
    assert client.post("/api/settlement/direct-document-groups/query", json={}).json()["total"] == 2
    app.dependency_overrides[current_owner] = lambda: "service:robot"
    assert (
        client.post(
            base + "/bills", json=dict(fileName="x.pdf", content=encoded(bill_pdf()), declarationNos=[])
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/settlement/direct-document-groups", json=create_body(["REAL871"]).model_dump()
        ).status_code
        == 403
    )
    cfg = _config(SCHEMA_INI, seeded.url.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError, match="已有直接收汇资料组"):
        command.downgrade(cfg, "0050_settlement_direct_documents")


def test_concurrent_creation_has_one_owner(seeded, tmp_path):
    if seeded.dialect.name != "mysql":
        pytest.skip("资料组并发占用仅在隔离 MySQL 中验证")
    docs = group_docs(seeded, tmp_path)

    def create_once(_):
        try:
            return docs.groups.create(create_body(["REAL872"]), "finance-user").id
        except ApiError as error:
            assert error.status == 409
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create_once, range(2)))
    assert sum(value is not None for value in outcomes) == 1
    assert docs.groups.query(DocumentGroupQuery()).total == 1
