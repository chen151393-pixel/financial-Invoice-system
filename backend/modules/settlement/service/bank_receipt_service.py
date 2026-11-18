"""银行收汇明细查询：收汇记录、三方代付标记、实际客户的回款路径与按收汇抬头汇总。

只读。收汇记录由银行流水表格导入写入，导入用例尚未实现。
"""

import math

from backend.core.errors import ApiError

from ..dao import bank_receipt_dao
from ..policy.amount_policy import money
from ..policy.route_policy import ROUTE_LABELS
from ..vo.bank_receipt_vo import BankReceipt, BankReceiptList, BankReceiptTotal

THIRD_PARTY = {"all": None, "yes": True, "no": False}


class BankReceiptService:
    def __init__(self, engine, candidates):
        self.engine = engine
        # 回款路径判定与报关应收汇共用同一套规则
        self.candidates = candidates

    def browse(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        filters = {
            "customer": body.customer,
            "receiving_company": body.receivingCompany,
            "date_from": body.receiptFrom,
            "date_to": body.receiptTo,
            "third_party": THIRD_PARTY[body.thirdParty],
        }
        page = body.page
        with self.engine.connect() as connection:
            total, rows = bank_receipt_dao.page(
                connection, filters, (page - 1) * body.pageSize, body.pageSize
            )
            if rows == [] and total and page > 1:
                page = math.ceil(total / body.pageSize)
                total, rows = bank_receipt_dao.page(
                    connection, filters, (page - 1) * body.pageSize, body.pageSize
                )
            totals = bank_receipt_dao.totals(connection, filters)
        return BankReceiptList(
            items=[self._view(row) for row in rows],
            total=total,
            page=page,
            pageSize=body.pageSize,
            totals=[
                BankReceiptTotal(
                    receivingCompany=row["receiving_company"],
                    currency=row["currency"],
                    count=row["count"],
                    amount=str(money(row["amount"])),
                    thirdPartyCount=int(row["third_party_count"] or 0),
                    thirdPartyAmount=str(money(row["third_party_amount"])),
                )
                for row in totals
            ],
        )

    def _view(self, row):
        route, _ = self.candidates.route(row["customer_name"])
        return BankReceipt(
            id=row["id"],
            receiptDate=str(row["receipt_date"]),
            receivingCompany=row["receiving_company"],
            receivingAccount=row["receiving_account"] or "",
            payerName=row["payer_name"],
            customerName=row["customer_name"],
            thirdParty=row["payer_key"] != row["customer_key"],
            currency=row["currency"],
            amount=str(money(row["amount"])),
            reference=row["reference"] or "",
            route=route,
            routeLabel=ROUTE_LABELS[route],
        )
