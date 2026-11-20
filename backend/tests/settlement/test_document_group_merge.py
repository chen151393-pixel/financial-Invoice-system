"""单票组与合并流程：保留原资料、共享提单、跨抬头合同、预览失效及 MySQL 并发。"""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.core.middleware import register_error_handlers
from backend.manage import SCHEMA_INI, _config
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.controller.document_group_controller import create_router
from backend.modules.settlement.dao import document_group_dao as dao
from backend.modules.settlement.dto.bill_dto import UpdateBillRequest
from backend.modules.settlement.dto.document_group_dto import DocumentGroupQuery
from backend.modules.settlement.dto.document_merge_dto import (
    DocumentMergePreviewRequest,
    DocumentMergeQuery,
    MergeDocumentGroupsRequest,
)
from backend.modules.settlement.dto.document_reference import DocumentGroupRef
from backend.modules.settlement.dto.ledger_dto import LedgerQuery
from backend.modules.settlement.dto.overview_dto import OverviewQuery
from backend.modules.settlement.entity.batch import settlement_batches
from backend.modules.settlement.service.document_merge_service import DocumentMergeService
from backend.modules.settlement.service.ledger_service import LedgerService
from backend.modules.settlement.service.overview_service import OverviewService
from backend.tests.settlement.documents_support import SELLER
from backend.tests.settlement.test_direct_documents import direct_documents
from backend.tests.settlement.test_document_groups import group_docs, make_direct
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_batches import services
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select


def preview_body(numbers, source="REAL870", bill=None):
    return DocumentMergePreviewRequest(sourceDeclarationNo=source, declarationNos=numbers, sharedBillId=bill)


def confirm(service, body, request_id=None):
    preview = service.preview(body)
    request = MergeDocumentGroupsRequest(
        **{**body.model_dump(), "sharedBillId": preview.sharedBillId},
        requestId=request_id or str(uuid.uuid4()),
        previewToken=preview.token,
    )
    return service.merge(request, "finance-user"), request


def test_single_groups_merge_preserves_files_and_money(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    single = direct_documents(seeded, tmp_path)
    single.party("ACME LTD", "ACME LTD")
    seller = single.party(SELLER, "EXPORT A")
    docs = group_docs(seeded, tmp_path)
    service = DocumentMergeService(docs.groups)
    a = docs.groups.ensure_single("REAL870", "finance-user")
    b = docs.groups.ensure_single("REAL871", "finance-user")
    assert a.kind == "single" and a.merge.allowed
    assert docs.groups.ensure_single("REAL870", "finance-user").id == a.id
    ba = docs.upload(DocumentGroupRef(a.id)).bills[0]
    ca = docs.generate(DocumentGroupRef(a.id), seller.id).contracts[0]
    bb = docs.upload(DocumentGroupRef(b.id)).bills[0]
    cb = docs.generate(DocumentGroupRef(b.id), seller.id).contracts[0]
    candidates, _ = services(seeded)
    ledger, overview = LedgerService(seeded, candidates), OverviewService(seeded, candidates)
    before = (ledger.query(LedgerQuery()), overview.query(OverviewQuery()))
    with seeded.connect() as conn:
        batch_count = conn.scalar(select(func.count()).select_from(settlement_batches))
    queried = service.query(DocumentMergeQuery(sourceDeclarationNo="REAL870"))
    assert queried.source.source and any(r.declarationNo == "REAL871" and r.sharedBill for r in queried.items)
    body = preview_body(["REAL870", "REAL871"])
    planned = service.preview(body)
    assert planned.merge.allowed and planned.amount == "1000.50"
    assert planned.sharedBillId == ba.id and len(planned.contracts) == 1
    merged, request = confirm(service, body)
    target = DocumentGroupRef(merged.id)
    assert merged.kind == "multiple" and not merged.merge.allowed
    assert service.merge(request, "finance-user").id == merged.id
    assert docs.groups.get(a.id).id == merged.id and docs.groups.get(b.id).id == merged.id
    assert docs.groups.query(DocumentGroupQuery()).total == 1
    assert docs.groups.query(DocumentGroupQuery(grouping="single")).total == 0
    view = docs.views.get(target)
    assert {c.id for c in view.contracts} == {ca.id, cb.id}
    assert all(c.stale for c in view.contracts)
    assert {b.id for b in view.bills} == {ba.id, bb.id}
    assert next(b for b in view.bills if b.id == ba.id).declarationNos == ["REAL870", "REAL871"]
    assert docs.bills.file(DocumentGroupRef(a.id), ba.id)[1].startswith(b"%PDF-")
    assert docs.contracts.file(DocumentGroupRef(b.id), cb.id)[1].startswith(b"%PDF-")
    with pytest.raises(ApiError, match="已合并"):
        docs.bills.update(
            DocumentGroupRef(a.id),
            ba.id,
            UpdateBillRequest(
                blNo=ba.blNo,
                portOfLoading=ba.portOfLoading,
                portOfDischarge=ba.portOfDischarge,
                onBoardDate=ba.onBoardDate,
                declarationNos=["REAL870"],
            ),
            "finance-user",
        )
    assert docs.generate(target, None).complete
    assert (ledger.query(LedgerQuery()), overview.query(OverviewQuery())) == before
    with seeded.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(settlement_batches)) == batch_count
        assert dao.get(conn, a.id)["initial_declaration_nos"] == ["REAL870"]
        assert dao.get(conn, a.id)["merged_into_id"] == merged.id
    cfg = _config(SCHEMA_INI, seeded.url.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError, match="已有资料组合并记录"):
        command.downgrade(cfg, "0052_settlement_group_comments")


def test_merge_across_sellers_requires_current_preview_and_rejects_occupied_groups(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    service = DocumentMergeService(docs.groups)
    a = docs.groups.ensure_single("REAL870", "finance-user")
    docs.upload(DocumentGroupRef(a.id))
    body = preview_body(["REAL870", "REAL872"])
    planned = service.preview(body)
    assert len(planned.contracts) == 2
    assert {c.sellerName for c in planned.contracts} == {SELLER, "另一申报主体"}
    stale = MergeDocumentGroupsRequest(
        **{**body.model_dump(), "sharedBillId": planned.sharedBillId},
        requestId=str(uuid.uuid4()),
        previewToken=planned.token,
    )
    _import(CustomsReceiptService(seeded), [row("REAL872", "01", "墨水", "个", 10, "ACME LTD", total=1200)])
    with pytest.raises(ApiError, match="预览后"):
        service.merge(stale, "finance-user")
    assert docs.groups.query(DocumentGroupQuery()).total == 1
    merged, _ = confirm(service, body)
    assert merged.amount == "1800.00"
    occupied = service.preview(preview_body(["REAL870", "REAL871"]))
    assert not occupied.merge.allowed and not next(c for c in occupied.checks if c.key == "available").passed
    listed = service.query(DocumentMergeQuery(sourceDeclarationNo="REAL871"))
    assert not next(r for r in listed.items if r.declarationNo == "REAL870").select.allowed
    assert docs.groups.ensure_single("REAL872", "finance-user").id == merged.id


def test_merge_constraints_and_http(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    service = DocumentMergeService(docs.groups)
    source = docs.groups.ensure_single("REAL870", "finance-user")
    assert not service.preview(preview_body(["REAL870"])).merge.allowed
    assert not service.preview(preview_body(["REAL871", "REAL872"])).merge.allowed
    assert not service.preview(preview_body(["REAL870", "REAL870"])).merge.allowed
    assert not service.preview(preview_body(["REAL870", "UNKNOWN"])).merge.allowed
    assert not service.preview(preview_body(["REAL870", "REAL871"], bill=99999)).merge.allowed
    other = row("REAL871", "01", "墨水", "个", 10, "OTHER CUSTOMER", total=400.5)
    _import(CustomsReceiptService(seeded), [other])
    assert not next(
        c for c in service.preview(preview_body(["REAL870", "REAL871"])).checks if c.key == "customer"
    ).passed
    other[21] = "ACME LTD"
    other[14] = "EUR"
    _import(CustomsReceiptService(seeded), [other])
    assert not next(
        c for c in service.preview(preview_body(["REAL870", "REAL871"])).checks if c.key == "currency"
    ).passed
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_router(docs.groups, service))
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    client = TestClient(app)
    assert (
        client.post(
            "/api/settlement/direct-document-groups/single", json={"declarationNo": "REAL870"}
        ).json()["id"]
        == source.id
    )
    preview = client.post(
        "/api/settlement/direct-document-groups/merge/preview",
        json=preview_body(["REAL870", "REAL872"]).model_dump(),
    )
    assert preview.status_code == 200
    request = {
        **preview_body(["REAL870", "REAL872"]).model_dump(),
        "requestId": str(uuid.uuid4()),
        "previewToken": preview.json()["token"],
        "sharedBillId": preview.json()["sharedBillId"],
    }
    app.dependency_overrides[current_owner] = lambda: "service:robot"
    assert client.post("/api/settlement/direct-document-groups/merge", json=request).status_code == 403
    assert (
        client.post(
            "/api/settlement/direct-document-groups/single", json={"declarationNo": "REAL872"}
        ).status_code
        == 403
    )
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    merged = client.post("/api/settlement/direct-document-groups/merge", json=request)
    assert merged.status_code == 200, merged.text
    assert (
        client.get(f"/api/settlement/direct-document-groups/{source.id}").json()["id"] == merged.json()["id"]
    )


def test_mysql_concurrent_single_and_merge_has_one_owner(seeded, ns, tmp_path):
    if seeded.dialect.name != "mysql":
        pytest.skip("并发归属仅在隔离 MySQL 中验证")
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    service = DocumentMergeService(docs.groups)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: docs.groups.ensure_single("REAL870", "finance-user").id, range(2)))
    assert len(set(ids)) == 1
    bodies = [preview_body(["REAL870", "REAL871"]), preview_body(["REAL870", "REAL872"])]
    requests = [
        MergeDocumentGroupsRequest(
            **{**b.model_dump(), "sharedBillId": (p := service.preview(b)).sharedBillId},
            requestId=str(uuid.uuid4()),
            previewToken=p.token,
        )
        for b in bodies
    ]

    def do_merge(request):
        try:
            return service.merge(request, "finance-user").id
        except ApiError as error:
            assert error.status == 409
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(do_merge, requests))
    assert sum(v is not None for v in outcomes) == 1
    assert docs.groups.query(DocumentGroupQuery(grouping="multiple")).total == 1
