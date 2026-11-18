"""按银行导出格式验证入库、重传和冲突回滚。"""

from base64 import b64encode
from io import BytesIO

from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.modules.settlement.controller import bank_receipt_controller
from backend.modules.settlement.dto.ledger_dto import LedgerQuery
from backend.modules.settlement.service.bank_receipt_service import BankReceiptService
from backend.modules.settlement.service.candidate_service import CandidateService
from backend.modules.settlement.service.ledger_service import LedgerService
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from openpyxl import Workbook

API = "/api/settlement/bank-receipts"
HEADERS = [
    "交易类型[ Transaction Type ]",
    "付款人名称[ Payer's Name ]",
    "境外收货人名称",
    "收款人账号[ Payee's Account Number ]",
    "收款人名称[ Payee's Name ]",
    "交易日期[ Transaction Date ]",
    "交易时间[ Transaction time ]",
    "交易货币[ Trade Currency ]",
    "交易金额[ Trade Amount ]",
]
RECEIPT = [
    "来账",
    "PAY AGENT\t",
    "ACME LTD",
    "00123456\t",
    "上海毅鑫实业有限公司",
    "20261008\t",
    "09:01:17\t",
    "USD\t",
    9228.25,
]


def payload(*rows, filename="银行来账.xlsx"):
    book = Workbook()
    sheet = book.active
    sheet.append([None, None, "人工填写的业务列"])
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    book.save(stream)
    return {"filename": filename, "content": b64encode(stream.getvalue()).decode()}


def test_bank_upload_retries_and_rolls_back_conflicts(schema_engine):
    candidates = CandidateService(schema_engine)
    app = FastAPI()
    app.include_router(bank_receipt_controller.create_router(BankReceiptService(schema_engine, candidates)))
    app.dependency_overrides[current_owner] = lambda: "finance-user"

    @app.exception_handler(ApiError)
    def api_error(_request: Request, error: ApiError):
        return JSONResponse({"message": error.message}, status_code=error.status)

    with TestClient(app) as client:
        outbound = ["往账", *RECEIPT[1:]]
        uploaded = client.post(f"{API}/import", json=payload(RECEIPT, outbound))
        assert uploaded.status_code == 200
        assert uploaded.json() == {"imported": 1, "duplicates": 0, "ignored": 1}

        retry = client.post(f"{API}/import", json=payload(RECEIPT, filename="重叠区间.xlsx"))
        assert retry.json() == {"imported": 0, "duplicates": 1, "ignored": 0}

        candidate = [*RECEIPT[:6], "10:00:00", *RECEIPT[7:]]
        conflict = [*RECEIPT[:2], "OTHER LTD", *RECEIPT[3:]]
        failed = client.post(f"{API}/import", json=payload(candidate, conflict))
        assert failed.status_code == 409
        assert "第 4 行" in failed.json()["message"]

        missing_customer = [*RECEIPT[:2], None, *RECEIPT[3:]]
        invalid = client.post(f"{API}/import", json=payload(candidate, missing_customer))
        assert invalid.status_code == 422
        assert "境外收货人名称不能为空" in invalid.json()["message"]

        listed = client.post(f"{API}/query", json={}).json()
        assert listed["total"] == 1
        receipt = listed["items"][0]
        assert receipt["receiptDate"] == "2026-10-08"
        assert receipt["receiptTime"] == "09:01:17"
        assert receipt["receivingAccount"] == "00123456"
        assert receipt["payerName"] == "PAY AGENT"
        assert receipt["customerName"] == "ACME LTD"
        assert receipt["thirdParty"] is True
        assert receipt["amount"] == "9228.25"
        assert receipt["reference"] == ""

    ledger = LedgerService(schema_engine, candidates).query(LedgerQuery())
    assert ledger.groups[0].consignee == "ACME LTD"
    assert ledger.groups[0].balance == "-9228.25"
