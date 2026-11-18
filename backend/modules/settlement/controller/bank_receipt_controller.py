"""银行收汇明细接口：只读查询；表格导入尚未实现。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.bank_receipt_dto import BankReceiptQuery
from ..vo.bank_receipt_vo import BankReceiptList


def create_router(bank_receipts):
    router = APIRouter(prefix="/api/settlement/bank-receipts", tags=["结汇银行收汇明细"])

    @router.post("/query", response_model=BankReceiptList)
    def query(body: BankReceiptQuery, owner: Owner):
        return bank_receipts.browse(body)

    return router
