"""资料组缺陷回归：来源恢复、PDF 原件、幂等恢复、去重打包与批量查询。"""

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
from backend.modules.settlement.controller.document_group_controller import create_router
from backend.modules.settlement.dao import bill_dao
from backend.modules.settlement.dao import document_group_dao as dao
from backend.modules.settlement.dto.document_group_dto import ConfirmGroupBasis, DocumentGroupQuery
from backend.modules.settlement.dto.document_reference import DocumentGroupRef
from backend.modules.settlement.entity.batch import settlement_batches
from backend.modules.settlement.service.document_group_basis_service import DocumentGroupBasisService
from backend.modules.settlement.service.document_merge_service import DocumentMergeService
from backend.tests.settlement.documents_support import SELLER, bill_pdf
from backend.tests.settlement.test_document_group_merge import confirm, preview_body
from backend.tests.settlement.test_document_groups import group_docs, make_direct
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import event, select


def corrected(engine, name="ACME CORRECTED", amount=1200):
    _import(CustomsReceiptService(engine), [row("REAL872", "01", "墨水", "个", 10, name, total=amount)])


def test_source_update_preserves_files_requires_current_preview_and_records_operator(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    group = docs.groups.ensure_single("REAL872", "finance-user")
    target = DocumentGroupRef(group.id)
    bill = docs.upload(target).bills[0]
    docs.party("ACME LTD", "ACME LTD")
    docs.party("另一申报主体", "EXPORT B")
    contract = docs.generate(target, None).contracts[0]
    with seeded.connect() as connection:
        before = list(connection.execute(select(settlement_batches)).mappings())
    corrected(seeded)
    assert not docs.groups.get(group.id).edit.allowed
    assert docs.groups.get(group.id).updateSource.allowed
    service = DocumentGroupBasisService(docs.groups)
    preview = service.preview(group.id)
    assert (preview.oldConsignee, preview.newConsignee, preview.amount) == (
        "ACME LTD",
        "ACME CORRECTED",
        "1200.00",
    )
    with pytest.raises(ApiError) as forbidden:
        service.confirm(group.id, ConfirmGroupBasis(token=preview.token), "service:robot")
    assert forbidden.value.status == 403
    corrected(seeded, amount=1300)
    with pytest.raises(ApiError, match="预览后"):
        service.confirm(group.id, ConfirmGroupBasis(token=preview.token), "finance-user")
    preview = service.preview(group.id)
    updated = service.confirm(group.id, ConfirmGroupBasis(token=preview.token), "finance-user")
    assert updated.edit.allowed and updated.consignee == "ACME CORRECTED" and updated.amount == "1300.00"
    assert not updated.updateSource.allowed
    view = docs.views.get(target)
    assert view.bills[0].id == bill.id and view.contracts[0].id == contract.id and view.contracts[0].stale
    docs.party("ACME CORRECTED", "ACME CORRECTED")
    assert docs.generate(target, None).complete
    with seeded.connect() as connection:
        history = dao.get(connection, group.id)["basis_history"]
        assert history[0]["before"]["consignee"] == "ACME LTD"
        assert history[0]["after"]["consignee"] == "ACME CORRECTED"
        assert history[0]["operator"] == "finance-user"
        assert list(connection.execute(select(settlement_batches)).mappings()) == before
    cfg = _config(SCHEMA_INI, seeded.url.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError, match="来源更新记录"):
        command.downgrade(cfg, "0054_settlement_hk_slips")


def test_source_update_refuses_mixed_customer_currency_and_merged_alias(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    a = docs.groups.ensure_single("REAL870", "finance-user")
    service = DocumentMergeService(docs.groups)
    group, _ = confirm(service, preview_body(["REAL870", "REAL872"]))
    corrected(seeded)
    basis = DocumentGroupBasisService(docs.groups)
    assert not basis.preview(group.id).update.allowed
    with pytest.raises(ApiError, match="客户"):
        basis.confirm(group.id, ConfirmGroupBasis(token=basis.preview(group.id).token), "finance-user")
    with pytest.raises(ApiError, match="已合并"):
        basis.preview(a.id)
    changed = row("REAL872", "01", "墨水", "个", 10, "ACME LTD", total=1000)
    changed[14] = "EUR"
    _import(CustomsReceiptService(seeded), [changed])
    assert not basis.preview(group.id).update.allowed
    assert "币种" in basis.preview(group.id).update.reason


def test_bill_rejects_broken_empty_encrypted_pdf_and_accepts_scan(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    target = DocumentGroupRef(docs.groups.ensure_single("REAL872", "finance-user").id)
    empty = io.BytesIO()
    PdfWriter().write(empty)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    encrypted = io.BytesIO()
    writer.write(encrypted)
    for content in (b"%PDF-1.4\nnot-a-pdf\n", empty.getvalue(), encrypted.getvalue()):
        with pytest.raises(ApiError) as rejected:
            docs.upload(target, content)
        assert rejected.value.status == 422
    assert docs.views.get(target).bills == []
    assert docs.upload(target, bill_pdf()).bills[0].blNo
    # 无文字层的有效扫描件仍可上传，由 OCR 或人工补填。
    from backend.tests.settlement.documents_support import scanned_bill_pdf

    assert docs.upload(target, scanned_bill_pdf()).bills


def test_package_deduplicates_shared_pdf_without_deleting_records(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    docs.party("ACME LTD", "ACME LTD")
    docs.party(SELLER, "EXPORT A")
    pdf = bill_pdf()
    for number in ("REAL870", "REAL871"):
        group = docs.groups.ensure_single(number, "finance-user")
        docs.upload(DocumentGroupRef(group.id), pdf)
    group, request = confirm(DocumentMergeService(docs.groups), preview_body(["REAL870", "REAL871"]))
    target = DocumentGroupRef(group.id)
    assert docs.generate(target, None).complete
    _, content = docs.packages.build(target)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        bills = [name for name in archive.namelist() if "/共用提单/" in name]
        assert len(bills) == 1 and archive.read(bills[0]) == pdf
        listing = archive.read(
            next(name for name in archive.namelist() if name.endswith("文件清单.txt"))
        ).decode()
        assert "REAL870" in listing and "REAL871" in listing
    with seeded.connect() as connection:
        rows = bill_dao.active(connection, target)
    assert len(rows) == 2
    # 即使是旧登记，打包时也拒绝损坏原件，不能把识别失败当成有效文件。
    docs.store.path(rows[0]["file_id"], "pdf").write_bytes(b"%PDF-1.4\nbroken\n")
    with pytest.raises(ApiError) as rejected:
        docs.packages.build(target)
    assert rejected.value.status == 422
    assert DocumentMergeService(docs.groups).result(request.requestId).id == group.id


def test_merge_result_http_distinguishes_pending_and_committed(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    merges = DocumentMergeService(docs.groups)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_router(docs.groups, merges))
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    client = TestClient(app)
    request_id = str(uuid.uuid4())
    path = f"/api/settlement/direct-document-groups/merge/requests/{request_id}"
    assert client.get(path).json() == {"group": None}
    group, request = confirm(merges, preview_body(["REAL870", "REAL871"]), request_id)
    assert client.get(path).json()["group"]["id"] == group.id
    assert not merges.preview(preview_body(["REAL870", "REAL871"])).merge.allowed
    assert merges.merge(request, "finance-user").id == group.id


def test_group_query_batches_history_and_preserves_status_pagination(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    for number in ("REAL870", "REAL871", "REAL872"):
        docs.groups.ensure_single(number, "finance-user")
    statements = []

    def count(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(seeded, "before_cursor_execute", count)
    assert docs.groups.query(DocumentGroupQuery(grouping="multiple")).total == 0
    assert len(statements) == 1
    statements.clear()
    initial = docs.groups.query(DocumentGroupQuery(grouping="single", pageSize=1))
    count_before = len(statements)
    event.remove(seeded, "before_cursor_execute", count)
    ids = [str(1000 + i) for i in range(12)]
    save(
        ns,
        seeded,
        bundle(
            [purchase(str(300 + i), number) for i, number in enumerate(ids)],
            [customs(number) for number in ids],
        ),
    )
    _import(
        CustomsReceiptService(seeded),
        [row(f"REAL{number}", "01", "墨水", "个", 10, "ACME LTD", total=100) for number in ids],
    )
    for number in ids:
        docs.groups.ensure_single(f"REAL{number}", "finance-user")
    statements.clear()
    event.listen(seeded, "before_cursor_execute", count)
    page = docs.groups.query(DocumentGroupQuery(grouping="single", pageSize=1))
    assert page.total == 15 and len(page.items) == 1
    assert len(statements) <= count_before + 1
    statements.clear()
    filtered = docs.groups.query(
        DocumentGroupQuery(grouping="single", status="pending_bill", pageSize=2, page=2)
    )
    assert filtered.total == 15 and len(filtered.items) == 2
    assert len(statements) <= count_before + 1
    event.remove(seeded, "before_cursor_execute", count)
    assert initial.total == 3
    keyword = docs.groups.query(DocumentGroupQuery(keyword="CD1000"))
    assert keyword.total == 1 and keyword.items[0].members[0].recordNo == "CD1000"


def test_mysql_concurrent_basis_update_is_recorded_once(seeded, ns, tmp_path):
    if seeded.dialect.name != "mysql":
        pytest.skip("来源更新并发在隔离 MySQL 验证")
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    group = docs.groups.ensure_single("REAL872", "finance-user")
    corrected(seeded)
    service = DocumentGroupBasisService(docs.groups)
    body = ConfirmGroupBasis(token=service.preview(group.id).token)

    def update(_):
        try:
            return service.confirm(group.id, body, "finance-user").id
        except ApiError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, range(2)))
    assert sorted(results) == sorted([group.id, 409])
    with seeded.connect() as connection:
        assert len(dao.get(connection, group.id)["basis_history"]) == 1


def test_single_group_currency_correction_can_resume_with_current_amount(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    group = docs.groups.ensure_single("REAL872", "finance-user")
    changed = row("REAL872", "01", "墨水", "个", 10, "ACME LTD", total=850)
    changed[14] = "EUR"
    _import(CustomsReceiptService(seeded), [changed])
    assert not docs.groups.get(group.id).edit.allowed
    service = DocumentGroupBasisService(docs.groups)
    preview = service.preview(group.id)
    assert preview.update.allowed and (preview.oldCurrency, preview.newCurrency) == ("USD", "EUR")
    updated = service.confirm(group.id, ConfirmGroupBasis(token=preview.token), "finance-user")
    assert updated.edit.allowed and updated.currency == "EUR" and updated.amount == "850.00"
