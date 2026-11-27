"""报关应收汇：逐单给出已收、未收、结汇阶段、账龄与资料状态，并按境外收货人汇总。只读。

已收推算需要完整历史（直接收汇先出口先冲抵），所以先读取全部报关单、银行收汇与有效香港批次，
在内存中计算后再按查询条件筛选；筛选不改变推算结果。
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from backend.core.errors import ApiError
from backend.core.names import normalize_name

from ..dao import bank_receipt_dao, batch_dao, batch_item_dao, bill_dao, contract_dao, document_group_dao
from ..policy import receivable_policy as rules
from ..policy.amount_policy import money
from ..policy.route_policy import DIRECT, HK_TRANSIT, ROUTE_LABELS
from ..vo.receivable_vo import (
    ReceivableCustomer,
    ReceivableItem,
    ReceivableList,
    ReceivableTotal,
    StageCount,
)
from .direct_document_source import DirectDocumentSource

ITEM_LIMIT = 500
CHINA = ZoneInfo("Asia/Shanghai")
ZERO = Decimal(0)
# 直接收汇的资料只做留存，以下状态才计为“资料待处理”
DIRECT_DOCUMENT_ISSUES = ("stale", "pending_bill", "pending_contract")
HK_DOCUMENT_ISSUES = ("pending", "stale")


def _amount(value):
    return str(money(value))


def china_today():
    return datetime.now(CHINA).date()


def _stage_counts(rows):
    counts = {stage: 0 for stage in rules.STAGES}
    for row in rows:
        counts[row["stage"]] += 1
    alerts = sum(1 for row in rows if row["alert"])
    result = [
        StageCount(stage=stage, label=rules.STAGE_LABELS[stage], count=count)
        for stage, count in counts.items()
        if count or stage != rules.ISSUE
    ]
    every = StageCount(stage="all", label="全部", count=len(rows))
    return [every, *result, StageCount(stage="alert", label="需要关注", count=alerts)]


class ReceivableService:
    def __init__(self, engine, candidates, reader, *, today=china_today):
        self.engine = engine
        # 回款路径判定、报关单读取与香港批次建批次共用同一套规则
        self.candidates = candidates
        self.reader = reader
        self.today = today

    def query(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            rows, overpaid, _, batches, items, today = self.snapshot(connection)
            selected = self._filter(rows, body)
            self._documents(connection, selected, batches, items)

        shown = [row for row in selected if _stage_match(row, body.stage)]
        shown.sort(key=_work_order)
        return ReceivableList(
            items=[_item(row) for row in shown[:ITEM_LIMIT]],
            total=len(shown),
            truncated=len(shown) > ITEM_LIMIT,
            stages=_stage_counts(selected),
            customers=_customers(selected, overpaid),
            totals=_totals(selected, overpaid),
            asOf=str(today),
        )

    def progress(self, body):
        """总览阶段分布复用完整收汇快照；不读取资料文件、不写入业务记录。"""
        from ..policy.settlement_progress_policy import describe
        from ..vo.progress_vo import SettlementProgress

        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            rows, _, _, _, _, today = self.snapshot(connection)
        wanted = normalize_name(body.consignee)
        selected = [
            row
            for row in rows
            if (not wanted or wanted in normalize_name(row["consignee"]))
            and (not body.currency or body.currency.upper() == row["currency"])
        ]
        currencies, excluded = describe(selected)
        return SettlementProgress(currencies=currencies, excludedCount=excluded, asOf=str(today))

    def snapshot(self, connection):
        """列表与单票详情共用的完整历史快照；不受列表筛选和 500 条显示上限影响。"""
        declarations = self.candidates.load(connection, limit=None)
        receipts = bank_receipt_dao.all_receipts(connection)
        occupied = batch_item_dao.active_numbers(connection)
        batch_ids = sorted(set(occupied.values()))
        batches, items = {}, {}
        if batch_ids:
            _, heads = batch_dao.page(connection, {"ids": batch_ids}, 0, len(batch_ids))
            batches = {head["id"]: head for head in heads}
            items = batch_item_dao.of_batches(connection, batch_ids)
        today = self.today()
        rows, overpaid = self._describe(declarations, receipts, occupied, batches, items, today)
        return rows, overpaid, receipts, batches, items, today

    def _describe(self, declarations, receipts, occupied, batches, items, today):
        """全部报关单的已收、阶段、账龄；推算基于完整历史。返回（逐单结果, 直接收汇超收）。"""
        direct_rows = [row for row in declarations if row["route"] == DIRECT and rules.usable(row)]
        direct_receipts = [
            row for row in receipts if self.candidates.route(row["customer_name"])[0] == DIRECT
        ]
        direct_paid, overpaid = rules.direct_received(direct_rows, direct_receipts)
        hk_paid = {}
        for batch_id, batch in batches.items():
            if batch["route"] == HK_TRANSIT:
                hk_paid.update(rules.hk_received(batch, items.get(batch_id, [])))
        result = []
        for row in declarations:
            batch_id = occupied.get(row["declaration_no"])
            batch = batches.get(batch_id) if batch_id is not None else None
            if row["route"] == HK_TRANSIT:
                received = hk_paid.get(row["declaration_no"], ZERO) if batch else ZERO
                basis = "已登记香港到账（到账 + 手续费）" if batch else "未登记回款"
            else:
                received = direct_paid.get(row["declaration_no"], ZERO)
                basis = "推算：同一收货人、收款抬头、币种先出口先冲抵"
            stage = rules.stage_of(row, received, batch["status"] if batch else None)
            usable = rules.usable(row)
            issue = row["currency_issue"] or ("" if row["consignee"] else "海关回执没有境外收货人")
            if not usable and not issue:
                issue = "海关回执没有可用金额"
            result.append(
                {
                    **row,
                    "usable": usable,
                    "issue": issue,
                    "batch": batch,
                    "received": received if usable else ZERO,
                    "outstanding": (row["amount"] - received) if usable else ZERO,
                    "basis": basis,
                    "stage": stage,
                    "aging": rules.aging_days(row, stage, today),
                    "alert": rules.alert_of(row, stage, batch, today),
                    "document": ("unavailable", ""),
                }
            )
        return result, overpaid

    def _filter(self, rows, body):
        wanted = normalize_name(body.consignee)
        result = []
        for row in rows:
            if wanted and wanted not in normalize_name(row["consignee"]):
                continue
            if body.currency and body.currency.upper() != row["currency"]:
                continue
            if body.declarationNo and body.declarationNo not in row["declaration_no"]:
                continue
            if body.route != "all" and row["route"] != body.route:
                continue
            if body.exportFrom and not (row["export_date"] and row["export_date"] >= body.exportFrom):
                continue
            if body.exportTo and not (row["export_date"] and row["export_date"] <= body.exportTo):
                continue
            result.append(row)
        return result

    def _documents(self, connection, rows, batches, items):
        """资料状态：香港中转读所在批次（只对办资料中的批次读取齐全度），直接收汇读该报关单已办理的资料。"""
        contexts = {}
        for batch_id in {
            row["batch"]["id"] for row in rows if row["batch"] and row["batch"]["status"] == "collected"
        }:
            contexts[batch_id] = (batches[batch_id], items.get(batch_id, []))
        direct = [row["declaration_no"] for row in rows if row["route"] == DIRECT and row["usable"]]
        owners = bill_dao.direct_owners(connection, direct) | contract_dao.direct_owners(connection, direct)
        groups = document_group_dao.by_numbers(connection, direct)
        owners |= set(groups)
        direct_contexts = DirectDocumentSource(self.candidates).for_rows(
            connection,
            [
                row
                for row in rows
                if row["route"] == DIRECT and row["usable"] and row["declaration_no"] in owners
            ],
            groups,
        )
        contexts.update({context["id"]: (context, linked) for context, linked in direct_contexts.values()})
        states = self.reader.states(connection, contexts)
        for row in rows:
            if row["route"] == HK_TRANSIT:
                batch = row["batch"]
                state = states.get(batch["id"]) if batch else None
                row["document"] = rules.hk_document_status(batch["status"] if batch else None, state)
            elif not row["usable"]:
                row["document"] = ("unavailable", row["issue"])
            else:
                owned = row["declaration_no"] in owners
                state = None
                if owned:
                    context, _ = direct_contexts[row["declaration_no"]]
                    state = states[context["id"]]
                row["document"] = rules.direct_document_status(owned, state)


def _stage_match(row, stage):
    if stage == "all":
        return True
    if stage == "alert":
        return bool(row["alert"])
    return row["stage"] == stage


def _work_order(row):
    """待办在前：未结汇的按等待天数从长到短，已结汇按出口日期从近到远。"""
    settled = row["stage"] == rules.SETTLED
    day = row["export_date"].toordinal() if row["export_date"] else 0
    return (settled, -(row["aging"] if row["aging"] is not None else -1), -day if settled else day)


def _item(row):
    batch = row["batch"]
    status, note = row["document"]
    width, text = rules.received_percent(row["received"], row["amount"] if row["usable"] else None)
    return ReceivableItem(
        declarationNo=row["declaration_no"],
        recordNo=row["record_no"],
        consignee=row["consignee"],
        exportCompany=row["export_company"],
        exportDate="" if row["export_date"] is None else str(row["export_date"]),
        salesOrders=row["sales_orders"],
        currency=row["currency"],
        amount="" if row["amount"] is None else _amount(row["amount"]),
        route=row["route"],
        routeLabel=ROUTE_LABELS[row["route"]],
        routeBasis=row["route_basis"],
        receivedAmount=_amount(row["received"]),
        outstandingAmount=_amount(row["outstanding"]),
        receivedBasis=row["basis"],
        receivedPercent=width,
        receivedPercentText=text,
        stage=row["stage"],
        stageLabel=rules.STAGE_LABELS[row["stage"]],
        agingDays=row["aging"],
        alert=row["alert"],
        issue=row["issue"],
        batchId=batch["id"] if batch else None,
        batchNo=(batch["batch_no"] or str(batch["id"])) if batch else "",
        documentStatus=status,
        documentLabel=rules.DOCUMENT_LABELS[status],
        documentNote=note,
    )


def _overpaid_of(overpaid, consignee, currency):
    key = normalize_name(consignee)
    return sum((value for (name, cur, _), value in overpaid.items() if name == key and cur == currency), ZERO)


def _customers(rows, overpaid):
    groups = {}
    for row in rows:
        key = (normalize_name(row["consignee"]), row["currency"])
        groups.setdefault(key, []).append(row)
    result = []
    for (_, currency), members in groups.items():
        first = members[0]
        hk = first["route"] == HK_TRANSIT
        usable = [row for row in members if row["usable"]]
        dates = sorted(row["export_date"] for row in members if row["export_date"])
        amount = sum((row["amount"] for row in usable), ZERO)
        received = sum((row["received"] for row in usable), ZERO)
        width, text = rules.received_percent(received, amount)
        agings = [row["aging"] for row in usable if row["aging"] is not None]
        issues = HK_DOCUMENT_ISSUES if hk else DIRECT_DOCUMENT_ISSUES
        document_issues = sum(1 for row in usable if row["document"][0] in issues)
        if hk:
            waiting = sum(1 for row in usable if row["stage"] == rules.UNREGISTERED)
            parts = [f"{document_issues} 票资料未齐"] if document_issues else []
            if waiting:
                parts.append(f"{waiting} 票登记回款后办理")
            note = " · ".join(parts) or "资料按批次办理"
        else:
            kept = sum(1 for row in usable if row["document"][0] == "kept")
            note = f"留存 {kept}/{len(usable)} 齐 · 不影响结汇"
        result.append(
            {
                "sort": (
                    -sum((row["outstanding"] for row in usable), ZERO),
                    first["consignee"].casefold(),
                    currency,
                ),
                "vo": ReceivableCustomer(
                    consignee=first["consignee"],
                    currency=currency,
                    route=first["route"],
                    routeLabel=ROUTE_LABELS[first["route"]],
                    routeBasis=first["route_basis"],
                    handling="batch" if hk else "ledger",
                    exportCompanies=sorted(
                        {row["export_company"] for row in members if row["export_company"]}
                    ),
                    count=len(members),
                    issueCount=len(members) - len(usable),
                    firstExportDate=str(dates[0]) if dates else "",
                    lastExportDate=str(dates[-1]) if dates else "",
                    amount=_amount(amount),
                    receivedAmount=_amount(received),
                    outstandingAmount=_amount(sum((row["outstanding"] for row in usable), ZERO)),
                    overpaidAmount=_amount(
                        ZERO if hk else _overpaid_of(overpaid, first["consignee"], currency)
                    ),
                    receivedPercent=width,
                    receivedPercentText=text,
                    stages=[
                        StageCount(stage=stage, label=rules.STAGE_LABELS[stage], count=count)
                        for stage in rules.STAGES
                        if (count := sum(1 for row in members if row["stage"] == stage))
                    ],
                    oldestAgingDays=max(agings) if agings else None,
                    batchedCount=sum(1 for row in members if row["batch"]),
                    pendingCount=sum(1 for row in usable if row["stage"] == rules.UNREGISTERED),
                    alertCount=sum(1 for row in members if row["alert"]),
                    documentIssueCount=document_issues,
                    documentNote=note,
                ),
            }
        )
    result.sort(key=lambda group: group["sort"])
    return [group["vo"] for group in result]


def _totals(rows, overpaid):
    """每个币种给出合计、香港中转、直接收汇三行；没有记录的路径为零。"""
    result = []
    for currency in sorted({row["currency"] for row in rows if row["usable"]}):
        same = [row for row in rows if row["usable"] and row["currency"] == currency]
        names = {normalize_name(row["consignee"]) for row in same if row["route"] == DIRECT}
        extra = sum(
            (value for (name, cur, _), value in overpaid.items() if cur == currency and name in names), ZERO
        )
        for route in ("all", HK_TRANSIT, DIRECT):
            members = same if route == "all" else [row for row in same if row["route"] == route]
            pending = [row for row in members if row["stage"] == rules.UNREGISTERED]
            result.append(
                ReceivableTotal(
                    route=route,
                    routeLabel="合计" if route == "all" else ROUTE_LABELS[route],
                    currency=currency,
                    count=len(members),
                    amount=_amount(sum((row["amount"] for row in members), ZERO)),
                    receivedAmount=_amount(sum((row["received"] for row in members), ZERO)),
                    outstandingAmount=_amount(sum((row["outstanding"] for row in members), ZERO)),
                    overpaidAmount=_amount(ZERO if route == HK_TRANSIT else extra),
                    pendingCount=len(pending),
                    pendingAmount=_amount(sum((row["amount"] for row in pending), ZERO)),
                )
            )
    return result
