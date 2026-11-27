"""银行收汇明细的导入与查询。"""

import math
from datetime import UTC, datetime

from backend.core import write_lock
from backend.core.errors import ApiError

from ..dao import bank_receipt_dao
from ..dto.bank_receipt_dto import MAX_IMPORT_BYTES
from ..policy.amount_policy import money
from ..policy.consignee_policy import consignee_key
from ..policy.receiving_company_policy import company_totals
from ..policy.route_policy import ROUTE_LABELS
from ..vo.bank_receipt_vo import BankReceipt, BankReceiptImportResult, BankReceiptList, BankReceiptTotal
from .bank_receipt_parser import parse_bank_receipts
from .bill_service import decode
from .consignee_service import register

THIRD_PARTY = {"all": None, "yes": True, "no": False}


class BankReceiptService:
    def __init__(self, engine, candidates):
        self.engine = engine
        # 回款路径判定与报关应收汇共用同一套规则
        self.candidates = candidates

    def import_file(self, body, owner):
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能导入银行流水")
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        filename = body.filename.strip()
        if any(char in filename for char in ("/", "\\", "\x00")) or not filename.lower().endswith(".xlsx"):
            raise ApiError(422, "请选择银行导出的 .xlsx 工作簿")
        entries, ignored = parse_bank_receipts(decode(body.content, MAX_IMPORT_BYTES, "银行流水"))
        now = datetime.now(UTC).replace(tzinfo=None)
        with write_lock.transaction(self.engine, scope="settlement-bank-receipts") as connection:
            known = bank_receipt_dao.by_import_keys(connection, list({row["import_key"] for row in entries}))
            added = []
            for row in entries:
                key = row["import_key"]
                stored = known.get(key)
                if stored is not None:
                    if consignee_key(stored["customer_key"]) != consignee_key(row["customer_key"]) or any(
                        stored[field] != row[field] for field in ("payer_key", "amount")
                    ):
                        raise ApiError(
                            409, f"第 {row['source_row']} 行与同一笔流水的客户、付款人或金额冲突，请核对"
                        )
                    continue
                known[key] = row
                added.append({**row, "source_file": filename, "imported_by": owner, "imported_at": now})
            if added:
                bank_receipt_dao.insert_many(connection, added)
            register(connection, (row["customer_name"] for row in entries), now)
        return BankReceiptImportResult(
            imported=len(added), duplicates=len(entries) - len(added), ignored=ignored
        )

    def browse(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        filters = {
            "receiving_company": body.receivingCompany,
            "date_from": body.receiptFrom,
            "date_to": body.receiptTo,
            "third_party": THIRD_PARTY[body.thirdParty],
        }
        page = body.page
        with self.engine.connect() as connection:
            display = self.candidates.display_names(connection)
            if body.customer:
                wanted = consignee_key(body.customer)
                filters["ids"] = [
                    id_
                    for id_, name in bank_receipt_dao.customers(connection)
                    if wanted in consignee_key(name)
                ]
            total, rows = bank_receipt_dao.page(
                connection, filters, (page - 1) * body.pageSize, body.pageSize
            )
            if rows == [] and total and page > 1:
                page = math.ceil(total / body.pageSize)
                total, rows = bank_receipt_dao.page(
                    connection, filters, (page - 1) * body.pageSize, body.pageSize
                )
            totals = company_totals(bank_receipt_dao.totals(connection, filters))
        return BankReceiptList(
            items=[self._view(row, display) for row in rows],
            total=total,
            page=page,
            pageSize=body.pageSize,
            totals=[
                BankReceiptTotal(
                    receivingCompany=row["receiving_company"],
                    featuredCompany=row["featured_company"],
                    currency=row["currency"],
                    count=row["count"],
                    amount=str(money(row["amount"])),
                    thirdPartyCount=int(row["third_party_count"] or 0),
                    thirdPartyAmount=str(money(row["third_party_amount"])),
                )
                for row in totals
            ],
        )

    def _view(self, row, display):
        route, _ = self.candidates.route(row["customer_name"])
        return BankReceipt(
            id=row["id"],
            receiptDate=str(row["receipt_date"]),
            receiptTime=str(row["receipt_time"]) if row["receipt_time"] is not None else "",
            receivingCompany=row["receiving_company"],
            receivingAccount=row["receiving_account"] or "",
            payerName=row["payer_name"],
            customerName=display.display_name(row["customer_name"]),
            thirdParty=row["payer_key"] != row["customer_key"],
            currency=row["currency"],
            amount=str(money(row["amount"])),
            reference=row["reference"] or "",
            route=route,
            routeLabel=ROUTE_LABELS[route],
        )
