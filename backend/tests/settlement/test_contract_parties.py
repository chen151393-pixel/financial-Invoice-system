"""合同双方来自报关依据，覆盖篡改卖方、NS 换版、买方换版、多合同与冲突。"""

import io

import pytest
from backend.core.errors import ApiError
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.dto.contract_dto import GenerateContractsRequest
from backend.tests.settlement.documents_support import HK, SELLER, Documents
from backend.tests.settlement.test_direct_documents import direct_documents
from backend.tests.settlement.test_settlement_batches import create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns
from pypdf import PdfReader


def generate(docs, reference, **extra):
    return docs.contracts.generate(
        reference,
        GenerateContractsRequest(paymentTermsCn="预付", paymentTermsEn="In advance", **extra),
        "finance-user",
    )


def change_declarant(ns, engine, number, name, company_id="9"):
    source_id, head, lines = customs(number, modified="2026-11-19T12:00:00Z")
    head["custrecord_swc_piname"] = {"id": company_id, "refName": name}
    purchase_id = {"870": "200", "871": "201", "872": "202"}[number]
    saved = save(ns, engine, bundle([purchase(purchase_id, number)], [(source_id, head, lines)]))
    assert not saved.get("skipped"), saved


def prepare_direct(engine, root):
    docs = direct_documents(engine, root)
    docs.party("ACME LTD", "ACME BUYER")
    docs.party(SELLER, "SOURCE EXPORTER")
    docs.upload("REAL872")
    return docs


def test_direct_parties_auto_fill_and_reject_manual_override(seeded, tmp_path):
    docs = prepare_direct(seeded, tmp_path)
    wrong = docs.party("无关公司", "WRONG EXPORTER")
    view = docs.views.get("REAL872")
    (expected,) = view.planned
    assert (expected.buyerName, expected.sellerName) == ("ACME LTD", "申报主体")
    assert [seller.name for seller in view.sellers] == ["申报主体"]
    with pytest.raises(ApiError, match="必须与对应 NS 报关单"):
        generate(docs, "REAL872", sellerPartyId=wrong.id)
    result = generate(docs, "REAL872")
    (contract,) = result.contracts
    assert (contract.buyerName, contract.sellerName) == ("ACME LTD", "申报主体")
    pdf = docs.contracts.file("REAL872", contract.id)[1]
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "ACME BUYER" in text and "SOURCE EXPORTER" in text and "WRONG EXPORTER" not in text


def test_changed_ns_declarant_and_consignee_invalidate_contract(seeded, ns, tmp_path):
    docs = prepare_direct(seeded, tmp_path)
    generate(docs, "REAL872")
    change_declarant(ns, seeded, "872", "新申报主体")
    changed = docs.views.get("REAL872")
    assert changed.planned[0].sellerName == "新申报主体"
    assert changed.contracts[0].stale and not changed.package.allowed and not changed.generate.allowed
    with pytest.raises(ApiError, match="未维护卖方合同抬头：新申报主体"):
        generate(docs, "REAL872")
    docs.party("新申报主体", "NEW SOURCE EXPORTER")
    assert not generate(docs, "REAL872").contracts[0].stale
    _import(CustomsReceiptService(seeded), [row("REAL872", "01", "墨水", "个", 10, "NEW BUYER", total=1000)])
    changed = docs.views.get("REAL872")
    assert changed.buyerName == "NEW BUYER" and changed.contracts[0].stale
    assert not changed.generate.allowed and changed.planned[0].buyerName == "NEW BUYER"
    docs.party("NEW BUYER", "NEW BUYER COMPANY")
    ready = generate(docs, "REAL872")
    assert ready.complete and ready.contracts[0].buyerName == "NEW BUYER"
    assert ready.contracts[0].sellerName == "新申报主体"


def test_hk_same_contract_rejects_conflicting_source_parties(seeded, ns, tmp_path):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "1000.50")
    docs = Documents(seeded, tmp_path)
    docs.party(HK, HK)
    docs.party(SELLER, "SOURCE EXPORTER")
    docs.party("另一申报主体", "OTHER EXPORTER")
    docs.upload(batch.id)
    change_declarant(ns, seeded, "871", "另一申报主体")
    view = docs.views.get(batch.id)
    assert not view.generate.allowed and "申报抬头不一致" in view.generate.reason
    with pytest.raises(ApiError, match="申报抬头不一致"):
        generate(docs, batch.id)
    _import(
        CustomsReceiptService(seeded), [row("REAL871", "01", "墨水", "个", 10, "OTHER BUYER", total=400.5)]
    )
    assert any("境外收货人不一致" in issue for issue in docs.views.get(batch.id).issues)


def test_distinct_hk_contracts_resolve_each_own_declarant(seeded, ns, tmp_path):
    second = row("REAL871", "01", "墨水", "个", 10, HK, total=400.5)
    second[9] = "OTHER-CONTRACT"
    _import(CustomsReceiptService(seeded), [second])
    change_declarant(ns, seeded, "871", "另一申报主体")
    _, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "1000.50")
    docs = Documents(seeded, tmp_path)
    docs.party(HK, HK)
    docs.party(SELLER, "SOURCE EXPORTER")
    docs.party("另一申报主体", "OTHER EXPORTER")
    docs.upload(batch.id)
    view = docs.views.get(batch.id)
    assert view.generate.allowed and view.defaults.sellerPartyId is None
    contracts = generate(docs, batch.id).contracts
    assert {item.contractNo: item.sellerName for item in contracts} == {
        "OTHER-CONTRACT": "另一申报主体",
        "YEX260827": "申报主体",
    }
    assert all(item.buyerName == HK for item in contracts)
