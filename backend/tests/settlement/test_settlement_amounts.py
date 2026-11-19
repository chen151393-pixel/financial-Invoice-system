"""银行金额输入：千分位须严格分组，Decimal 精度与安全字段提示贯穿 HTTP 边界。"""

from decimal import Decimal
from uuid import uuid4

import pytest
from backend.core.middleware import register_error_handlers
from backend.modules.settlement.dto.batch_dto import (
    CandidateQuery,
    CreateBatchRequest,
    RemittanceRequest,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


def body(**changes):
    return {
        "requestId": str(uuid4()),
        "declarationNos": ["310120260514395336"],
        "receivedOn": "2026-11-19",
        "receivedAmount": "10,002.59",
        "receivedFee": "0",
        **changes,
    }


@pytest.mark.parametrize("amount", ["10,002.59", "10002.59", " 10,002.59 "])
def test_receipt_amount_accepts_bank_grouping_without_float(amount):
    request = CreateBatchRequest.model_validate(body(receivedAmount=amount))
    assert request.receivedAmount == Decimal("10002.59")
    assert request.model_dump(mode="json")["receivedAmount"] == "10002.59"


def test_fee_recommendation_and_remittance_share_bank_amount_format():
    request = CreateBatchRequest.model_validate(body(receivedFee="1,234.50"))
    assert request.receivedFee == Decimal("1234.50")
    assert CandidateQuery(targetAmount="10,002.59").targetAmount == "10002.59"
    remittance = RemittanceRequest.model_validate(
        {"remittedOn": "2026-11-19", "remittedAmount": "10,002.59", "remittedFee": "1,234.50"}
    )
    assert remittance.remittedAmount == Decimal("10002.59")
    assert remittance.remittedFee == Decimal("1234.50")


@pytest.mark.parametrize(
    "amount",
    ["10,02.59", "1,00,002.59", "1,,002.59", "1000,002.59", "1,234,", "10.002,59"],
)
def test_bad_grouping_is_not_silently_reinterpreted(amount):
    with pytest.raises(ValidationError, match="千分位须每三位分组"):
        CreateBatchRequest.model_validate(body(receivedAmount=amount))


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "10000000000000000", "1.005"])
def test_precision_and_range_guards_are_preserved(amount):
    with pytest.raises(ValidationError):
        CreateBatchRequest.model_validate(body(receivedAmount=amount))


def test_zero_fee_allowed_but_negative_fee_rejected():
    assert CreateBatchRequest.model_validate(body()).receivedFee == 0
    with pytest.raises(ValidationError, match="手续费须为范围内的非负数"):
        CreateBatchRequest.model_validate(body(receivedFee="-1"))


def test_http_returns_safe_amount_field_errors_without_echoing_input():
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/api/settlement/batches")
    def parse_receipt(request: CreateBatchRequest):
        return {"amount": str(request.receivedAmount)}

    with TestClient(app) as client:
        assert client.post("/api/settlement/batches", json=body()).json() == {"amount": "10002.59"}
        response = client.post(
            "/api/settlement/batches",
            json=body(receivedAmount="private-bank-input", receivedFee="1.005", payer="private-payer"),
        )
        assert response.status_code == 400
        errors = response.json()["fieldErrors"]
        assert "到账金额不是有效数值" in errors["receivedAmount"]
        assert errors["receivedFee"] == "手续费最多两位小数"
        assert "手续费最多两位小数" in response.json()["error"]
        assert "private-" not in response.text
        extra = client.post("/api/settlement/batches", json=body(secret="private-secret"))
        assert extra.status_code == 400
        assert extra.json() == {"error": "请求字段缺失、类型错误或包含多余字段"}
        assert "private-" not in extra.text
