"""银行收汇明细接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.bank_receipt_dto import BankReceiptImportRequest, BankReceiptQuery
from ..vo.bank_receipt_vo import BankReceiptImportResult, BankReceiptList

JSON_BODY_LIMITS = {r"/api/settlement/bank-receipts/import": 6 * 1024 * 1024}


def create_router(bank_receipts):
    router = APIRouter(prefix="/api/settlement/bank-receipts", tags=["结汇银行收汇明细"])

    @router.post("/query", response_model=BankReceiptList)
    def query(body: BankReceiptQuery, owner: Owner):
        return bank_receipts.browse(body)

    @router.post("/import", response_model=BankReceiptImportResult)
    def import_file(body: BankReceiptImportRequest, owner: Owner):
        return bank_receipts.import_file(body, owner)

    return router
