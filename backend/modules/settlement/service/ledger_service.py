"""直接收汇明细（总账）：按出口与收汇汇总期初和期末差额。

只读。出口取报关应收汇中判定为直接收汇的报关单（海关回执出口日期与成交总价），
收汇取银行收汇明细中实际客户为直接收汇的记录；香港中转的报关单与汇回不进总账。
余额需要完整历史，因此每次读取全部直接收汇报关单与收汇记录后在内存中累计、筛选和分页。
"""

import math

from backend.core.errors import ApiError
from backend.core.names import normalize_name

from ..dao import bank_receipt_dao
from ..policy.amount_policy import money
from ..policy.consignee_policy import consignee_key
from ..policy.ledger_policy import (
    EXPORT,
    KIND_LABELS,
    STATUS_LABELS,
    build_groups,
    currency_totals,
    export_entry,
    receipt_entry,
)
from ..policy.route_policy import DIRECT
from ..vo.ledger_vo import LedgerEntry, LedgerGroup, LedgerList, LedgerSkipped, LedgerTotal


def _amount(value):
    return str(money(value))


def _entry(row):
    export = row["kind"] == EXPORT
    day = "" if row["date"] is None else str(row["date"])
    return LedgerEntry(
        kind=row["kind"],
        kindLabel=KIND_LABELS[row["kind"]],
        exportCompany=row["company"] if export else "",
        exportDate=day if export else "",
        exportAmount=_amount(row["amount"]) if export else "",
        receiptCompany="" if export else row["company"],
        receiptDate="" if export else day,
        receiptAmount="" if export else _amount(row["amount"]),
        sourceNo=row["source_no"],
        balance=_amount(row["balance"]),
        thirdParty=row["third_party"],
        payerName=row["payer"],
    )


class LedgerService:
    def __init__(self, engine, candidates):
        self.engine = engine
        # 回款路径判定与报关应收汇共用同一套规则
        self.candidates = candidates

    def query(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            display = self.candidates.display_names(connection)
            declarations = self.candidates.load(connection, limit=None)
            receipts = bank_receipt_dao.all_receipts(connection)
        entries, skipped = [], []
        for row in declarations:
            if row["route"] != DIRECT:
                continue
            reason = row["currency_issue"] or (
                "" if consignee_key(row["consignee"]) else "海关回执没有境外收货人"
            )
            if not reason and body.startDate and not row["export_date"]:
                reason = "海关回执没有出口日期"
            if reason:
                skipped.append(
                    LedgerSkipped(
                        declarationNo=row["declaration_no"],
                        consignee=display.display_name(row["consignee"]),
                        reason=reason,
                    )
                )
                continue
            entries.append(export_entry(row))
        for row in receipts:
            # 香港公司汇回境内的款项在香港中转批次登记，不进总账
            if self.candidates.route(row["customer_name"])[0] == DIRECT:
                entries.append(receipt_entry(row))
        if body.receivingCompany:
            recipient = normalize_name(body.receivingCompany)
            entries = [entry for entry in entries if recipient in normalize_name(entry["company"])]
        groups = build_groups(
            entries,
            start=body.startDate,
            end=body.endDate,
            by_recipient=body.byRecipient or bool(body.receivingCompany),
        )
        if body.consignee:
            wanted = consignee_key(body.consignee)
            groups = [group for group in groups if wanted in group["key"]]
        if body.company:
            company = normalize_name(body.company)
            groups = [
                group
                for group in groups
                if any(company in normalize_name(entry["company"]) for entry in group["entries"])
            ]
        if body.status != "all":
            groups = [group for group in groups if group["status"] == body.status]
        total = len(groups)
        page = min(body.page, max(1, math.ceil(total / body.pageSize)))
        shown = groups[(page - 1) * body.pageSize : page * body.pageSize]
        return LedgerList(
            groups=[
                LedgerGroup(
                    consignee=display.display_name(group["consignee"]),
                    receivingCompany=group["receiving_company"],
                    openingBalance=_amount(group["opening_balance"]),
                    currency=group["currency"],
                    exportTotal=_amount(group["export_total"]),
                    receiptTotal=_amount(group["receipt_total"]),
                    balance=_amount(group["balance"]),
                    status=group["status"],
                    statusLabel=STATUS_LABELS[group["status"]],
                    entries=[_entry(row) for row in group["entries"]],
                )
                for group in shown
            ],
            total=total,
            page=page,
            pageSize=body.pageSize,
            totals=[
                LedgerTotal(
                    currency=row["currency"],
                    openingBalance=_amount(row["opening_balance"]),
                    exportTotal=_amount(row["export_total"]),
                    receiptTotal=_amount(row["receipt_total"]),
                    balance=_amount(row["balance"]),
                    outstanding=_amount(row["outstanding"]),
                    overpaid=_amount(row["overpaid"]),
                    consigneeCount=sum(1 for g in groups if g["currency"] == row["currency"]),
                    exportCount=_count(groups, row["currency"], EXPORT),
                    receiptCount=_count(groups, row["currency"], "receipt"),
                )
                for row in currency_totals(groups)
            ],
            skipped=skipped,
        )


def _count(groups, currency, kind):
    return sum(
        1
        for group in groups
        if group["currency"] == currency
        for entry in group["entries"]
        if entry["kind"] == kind
    )
