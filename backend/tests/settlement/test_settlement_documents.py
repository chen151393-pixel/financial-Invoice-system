"""结汇资料用例：提单上传与解析 → 合同抬头 → 按模板生成销售合同 → 齐全度校验 → 资料包。"""

import io
import zipfile
from datetime import date

import pytest
from backend.core.errors import ApiError
from backend.modules.settlement.dto.bill_dto import UpdateBillRequest, UploadBillRequest
from backend.modules.settlement.policy.bill_parse_policy import english_date, parse_bill, parse_date
from backend.modules.settlement.policy.contract_policy import unit_price
from backend.tests.settlement.documents_support import (
    HK,
    SELLER,
    Documents,
    bill_pdf,
    complete_documents,
    encoded,
)
from backend.tests.settlement.test_settlement_batches import create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from pypdf import PdfReader


def test_parse_bill_fields_and_dates():
    text = (
        "Bill of Lading No. OOLU2156789012\nPort of Loading  Port of Discharge\n"
        "SHANGHAI\nShipped on board 15-JUN-2026"
    )
    parsed = parse_bill(text)
    assert parsed["bl_no"] == "OOLU2156789012" and parsed["on_board_date"] == date(2026, 6, 15)
    # 标签并排时取不到可靠的值，留空由人工填写，不猜测
    assert parsed["port_of_discharge"] == "" and parsed["port_of_loading"] == ""
    below = parse_bill("PORT OF LOADING\nNINGBO, CHINA\nPORT OF DISCHARGE\nSANTOS\n")
    assert (below["port_of_loading"], below["port_of_discharge"]) == ("NINGBO, CHINA", "SANTOS")
    same_line = parse_bill("B/L NO: EGLV142503975412\nPORT OF DISCHARGE: LOS ANGELES, CA\n")
    assert same_line["port_of_discharge"] == "LOS ANGELES, CA" and same_line["on_board_date"] is None
    assert parse_bill("")["bl_no"] == ""
    assert parse_date("2026/06/15") == date(2026, 6, 15) and parse_date("JUN 31 2026") is None
    assert (
        english_date(date(2026, 4, 9)) == "9th Apr 2026"
        and english_date(date(2026, 4, 22)) == "22nd Apr 2026"
    )
    assert str(unit_price("1099", "100")) == "10.9900" and unit_price("5", 0) is None


def test_documents_from_upload_to_package(seeded, tmp_path):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "985.50", fee="15.00")
    documents = Documents(seeded, tmp_path)

    empty = documents.views.get(batch.id)
    assert not empty.complete and empty.edit.allowed and not empty.package.allowed
    assert "报关单 REAL870 缺提单" in empty.issues and any("买方合同抬头" in i for i in empty.issues)
    assert [(p.contractNo, p.amount) for p in empty.planned] == [("YEX260827", "1000.50")]

    with pytest.raises(ApiError, match="须为 PDF"):
        documents.upload(batch.id, content=b"not a pdf")
    with pytest.raises(ApiError, match="不在本批次"):
        documents.upload(batch.id, numbers=["REAL872"])
    uploaded = documents.upload(batch.id).bills[0]
    assert (uploaded.blNo, uploaded.portOfLoading, uploaded.portOfDischarge, uploaded.onBoardDate) == (
        "EGLV142503975412",
        "YANTIAN, CHINA",
        "LOS ANGELES, CA",
        "2026-06-15",
    )
    assert uploaded.declarationNos == ["REAL870", "REAL871"] and uploaded.missing == []
    with pytest.raises(ApiError, match="已上传"):
        documents.upload(batch.id)
    assert documents.bills.file(batch.id, uploaded.id)[1].startswith(b"%PDF-")

    # 识别不出文字的提单：字段留空，等待人工填写
    blank = documents.upload(batch.id, content=bill_pdf(("SCANNED",)), numbers=["REAL871"]).bills[1]
    assert blank.missing == ["提单号", "装运口岸", "目的口岸", "装船日期"] and "人工填写" in blank.parseNote
    removed = documents.bills.remove(batch.id, blank.id, "finance-user")
    assert [bill.id for bill in removed.bills] == [uploaded.id]

    buyer = documents.party(HK, HK)
    seller = documents.party(SELLER, "SHANGHAI VISION DIGITAL PRINTING CO.,LTD.", stamp=False)
    with pytest.raises(ApiError, match="同名"):
        documents.party(HK.lower(), HK)
    with pytest.raises(ApiError, match="卖方不能与买方相同"):
        documents.generate(batch.id, buyer.id)
    ready = documents.views.get(batch.id)
    assert ready.generate.allowed and [s.name for s in ready.sellers] == [SELLER]

    generated = documents.generate(batch.id, seller.id)
    contract = generated.contracts[0]
    # 签订日期 = 出口日期 2026-10-29 往前推 28 天；金额只取海关回执成交总价
    assert (contract.contractNo, contract.amount, contract.contractDate) == (
        "YEX260827",
        "1000.50",
        "2026-10-01",
    )
    assert generated.complete and generated.package.allowed and not contract.stale
    assert generated.warnings == ["销售合同 YEX260827：卖方未上传印章，合同未盖该方印章"]
    name, content = documents.contracts.file(batch.id, contract.id)
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
    assert name == "销售合同YEX260827.pdf"
    assert "YEX260827" in text and "LOS ANGELES, CA" in text and "1000.50" in text and "1st Oct 2026" in text

    package_name, package = documents.packages.build(batch.id)
    names = zipfile.ZipFile(io.BytesIO(package)).namelist()
    root = package_name.removesuffix(".zip")
    assert sorted(names) == sorted(
        [
            f"{root}/YEX260827/销售合同YEX260827.pdf",
            f"{root}/YEX260827/提单EGLV142503975412.pdf",
            f"{root}/文件清单.txt",
        ]
    )

    # 提单口岸改动后合同依据变化：须重新生成，且不能确认资料已出、不能打包
    changed = documents.bills.update(
        batch.id,
        uploaded.id,
        UpdateBillRequest(
            blNo="EGLV142503975412",
            portOfLoading="Yantian, China",
            portOfDischarge="Long Beach, CA",
            onBoardDate="2026-06-15",
            declarationNos=["REAL870", "REAL871"],
        ),
        "finance-user",
    )
    assert changed.contracts[0].stale and not changed.complete
    assert changed.bills[0].portOfDischarge == "LONG BEACH, CA"
    with pytest.raises(ApiError, match="资料未齐"):
        batches.documents_ready(batch.id, "finance-user")
    with pytest.raises(ApiError, match="不能打包"):
        documents.packages.build(batch.id)
    old_file = documents.store.path(_file_id(seeded, contract.id), "pdf")
    regenerated = documents.generate(batch.id, seller.id)
    assert regenerated.complete and not old_file.exists()

    # 确认资料已出后资料只读，仍可下载
    assert batches.documents_ready(batch.id, "finance-user").status == "documents_ready"
    with pytest.raises(ApiError, match="资料不能再修改"):
        documents.upload(batch.id, content=bill_pdf(("OTHER",)))
    with pytest.raises(ApiError, match="资料不能再修改"):
        documents.generate(batch.id, seller.id)
    assert documents.packages.build(batch.id)[1].startswith(b"PK")


def _file_id(engine, contract_id):
    from backend.modules.settlement.entity.contract import settlement_contracts
    from sqlalchemy import select

    with engine.connect() as connection:
        query = select(settlement_contracts.c.file_id).where(settlement_contracts.c.id == contract_id)
        return connection.execute(query).scalar_one()


def test_direct_batch_needs_no_documents(seeded, tmp_path):
    _, batches = services(seeded)
    batch = create(batches, ["REAL872"], "1000")
    documents = Documents(seeded, tmp_path)
    view = documents.views.get(batch.id)
    assert not view.edit.allowed and view.edit.reason == "仅香港中转批次需要资料包"
    with pytest.raises(ApiError, match="仅香港中转"):
        documents.upload(batch.id)
    assert batches.settle(batch.id, "finance-user").status == "settled"


def test_upload_rejects_broken_content_and_helper_completes(seeded, tmp_path):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870"], "600")
    documents = Documents(seeded, tmp_path)
    with pytest.raises(ApiError, match="无法读取"):
        documents.bills.upload(
            batch.id, UploadBillRequest(fileName="a.pdf", content="@@not-base64@@"), "finance-user"
        )
    with pytest.raises(ApiError, match="服务身份只读"):
        documents.bills.upload(
            batch.id, UploadBillRequest(fileName="a.pdf", content=encoded(bill_pdf())), "service:sync"
        )
    assert not (tmp_path / "documents").exists() or list((tmp_path / "documents").iterdir()) == []
    complete_documents(seeded, tmp_path, batch.id)
    assert batches.get(batch.id).actions.documentsReady.allowed


def test_document_routes_bind_path_parameters():
    """下载接口按各自的路径参数取值，并以附件 / 内联方式返回文件。"""
    from backend.core.dependencies import current_owner
    from backend.modules.settlement.controller.document_controller import create_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    class Files:
        def file(self, batch_id, item_id):
            return f"文件{batch_id}-{item_id}.pdf", b"%PDF-demo"

        def build(self, batch_id):
            return f"资料包{batch_id}.zip", b"PK"

    app = FastAPI()
    app.include_router(create_router(None, Files(), Files(), Files()))
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    client = TestClient(app)
    bill = client.get("/api/settlement/batches/2/bills/7/file")
    contract = client.get("/api/settlement/batches/2/contracts/9/file")
    package = client.get("/api/settlement/batches/2/package")
    assert (bill.status_code, contract.status_code, package.status_code) == (200, 200, 200)
    assert contract.content == b"%PDF-demo" and contract.headers["content-type"] == "application/pdf"
    assert (
        "2-9.pdf" in contract.headers["content-disposition"]
        and "inline" in bill.headers["content-disposition"]
    )
    assert package.headers["content-disposition"].startswith("attachment;")
    assert client.get("/api/settlement/batches/2/contracts/0/file").status_code == 422
