"""报关应收汇：读取海关回执金额，判定回款路径，标出已被批次占用的报关单，并按金额推荐组合。

香港中转的报关单登记回款建批次；直接收汇（非香港中转）的报关单不建批次，进入直接收汇明细（总账）。
"""

from collections import defaultdict
from decimal import Decimal

from backend.core.errors import ApiError
from backend.core.names import normalize_name
from backend.modules.review.public import settlement_declarations
from backend.modules.source.public import declarant_names_by_number, declaration_refs_by_number

from ..dao import batch_dao, batch_item_dao
from ..policy.amount_policy import money, suggest_combination
from ..policy.route_policy import HK_TRANSIT, ROUTE_LABELS, hk_consignee_keys, route_of
from ..vo.batch_vo import Candidate, CandidateList, ConsigneeTotal, CurrencyTotal, RouteTotal

# 页面一次最多列出的报关单张数；汇总不受此限制
CANDIDATE_LIMIT = 500
HANDLING_LABELS = {"batch": "登记回款建批次", "ledger": "进直接收汇明细"}


def record_numbers(connection, numbers):
    """真实报关单号 → NS CD 编号；重号时以顿号列出全部。"""
    refs = declaration_refs_by_number(connection, numbers)
    return {number: "、".join(sorted(h["record_no"] or "" for h in heads)) for number, heads in refs.items()}


def describe(rows, record_nos, export_companies, occupied, batch_nos, hk_keys):
    """海关回执行 → 候选报关单 dict（含路径、处理方式与不可选原因）。"""
    result = []
    for row in rows:
        route, basis = route_of("", row["consignee"], hk_keys)
        blocked = row["currency_issue"]
        batch_id = occupied.get(row["declaration_no"])
        if batch_id is not None:
            blocked = f"已在结汇批次 {batch_nos.get(batch_id, batch_id)} 中"
        elif not row["consignee"]:
            blocked = "海关回执没有境外收货人"
        result.append(
            {
                **row,
                "route": route,
                "route_basis": basis,
                # 只有香港中转建批次；直接收汇进总账
                "handling": "batch" if route == HK_TRANSIT else "ledger",
                "blocked": blocked,
                "batch_no": "" if batch_id is None else str(batch_nos.get(batch_id, batch_id)),
                "record_no": record_nos.get(row["declaration_no"], ""),
                "export_company": export_companies.get(row["declaration_no"], ""),
            }
        )
    return result


class CandidateService:
    def __init__(self, engine, *, hk_consignees=(), fee_alert=Decimal("50")):
        self.engine = engine
        self.hk_keys = hk_consignee_keys(hk_consignees)
        self.fee_alert = fee_alert

    def _require_engine(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")

    def route(self, consignee):
        """境外收货人的回款路径与依据；银行收汇、直接收汇明细复用同一判定。"""
        return route_of("", consignee, self.hk_keys)

    def load(self, connection, *, numbers=None, consignee="", limit=CANDIDATE_LIMIT):
        """读取并判定候选报关单；建批次、直接收汇明细在各自连接中复用同一套规则。
        limit 为 None 时读取全部。"""
        rows = settlement_declarations(connection, numbers=numbers, consignee=consignee, limit=limit)
        numbers_found = [row["declaration_no"] for row in rows]
        occupied = batch_item_dao.active_by_numbers(connection, numbers_found)
        batch_nos = {}
        if occupied:
            _, heads = batch_dao.page(connection, {"ids": sorted(set(occupied.values()))}, 0, len(occupied))
            batch_nos = {head["id"]: head["batch_no"] for head in heads}
        return describe(
            rows,
            record_numbers(connection, numbers_found),
            declarant_names_by_number(connection, numbers_found),
            occupied,
            batch_nos,
            self.hk_keys,
        )

    def query(self, body):
        self._require_engine()
        with self.engine.connect() as connection:
            rows = self.load(connection, consignee=body.consignee, limit=None)
        if body.declarationNo:
            rows = [row for row in rows if body.declarationNo in row["declaration_no"]]
        if body.route != "all":
            rows = [row for row in rows if row["route"] == body.route]
        if body.exportFrom:
            rows = [row for row in rows if row["export_date"] and row["export_date"] >= body.exportFrom]
        if body.exportTo:
            rows = [row for row in rows if row["export_date"] and row["export_date"] <= body.exportTo]
        open_rows = [row for row in rows if not row["blocked"]]
        # 只有香港中转的报关单可以选入批次
        batchable = [row for row in open_rows if row["handling"] == "batch"]
        suggestion, note = None, ""
        if body.targetAmount:
            groups = {(row["consignee"], row["currency"]) for row in batchable}
            if len(groups) != 1:
                note = "请先按境外收货人筛选到同一家香港中转收货人、同一币种，再推荐组合"
            else:
                suggestion = suggest_combination(
                    [(row["declaration_no"], row["amount"]) for row in batchable], Decimal(body.targetAmount)
                )
                note = (
                    "已找到金额恰好吻合的报关单组合" if suggestion else "没有金额恰好吻合的组合，请人工勾选"
                )
        return CandidateList(
            items=[
                Candidate(
                    declarationNo=row["declaration_no"],
                    recordNo=row["record_no"],
                    consignee=row["consignee"],
                    exportCompany=row["export_company"],
                    exportDate="" if row["export_date"] is None else str(row["export_date"]),
                    salesOrders=row["sales_orders"],
                    currency=row["currency"],
                    amount="" if row["amount"] is None else str(money(row["amount"])),
                    route=row["route"],
                    routeLabel=ROUTE_LABELS[row["route"]],
                    routeBasis=row["route_basis"],
                    handling=row["handling"],
                    handlingLabel=HANDLING_LABELS[row["handling"]],
                    blockedReason=row["blocked"],
                    batchNo=row["batch_no"],
                )
                for row in rows[:CANDIDATE_LIMIT]
            ],
            total=len(rows),
            truncated=len(rows) > CANDIDATE_LIMIT,
            totals=_route_totals(rows),
            combinedTotals=_currency_totals(rows),
            unsettled=_route_totals(open_rows),
            consignees=_consignee_totals(rows),
            suggestion=suggestion,
            suggestionNote=note,
        )


def _route_totals(rows):
    """报关单金额按路径与币种汇总；金额缺失的报关单不计入。"""
    totals = defaultdict(lambda: [0, Decimal(0)])
    for row in rows:
        if row["amount"] is None:
            continue
        key = (row["route"], row["currency"])
        totals[key][0] += 1
        totals[key][1] += row["amount"]
    return [
        RouteTotal(
            route=route,
            routeLabel=ROUTE_LABELS[route],
            count=count,
            currency=currency,
            amount=str(money(total)),
        )
        for (route, currency), (count, total) in sorted(totals.items())
    ]


def _currency_totals(rows):
    """在同一筛选范围内合计两条回款路径，原始 Decimal 加总后再格式化。"""
    totals = defaultdict(lambda: [0, Decimal(0)])
    for row in rows:
        if row["amount"] is None:
            continue
        totals[row["currency"]][0] += 1
        totals[row["currency"]][1] += row["amount"]
    return [
        CurrencyTotal(currency=currency, count=count, amount=str(money(amount)))
        for currency, (count, amount) in sorted(totals.items())
    ]


def _consignee_totals(rows):
    """按（境外收货人, 币种）汇总应收汇：张数、出口日期范围、金额，以及香港中转的建批次进度。"""
    groups = {}
    for row in rows:
        key = (normalize_name(row["consignee"]), row["currency"])
        group = groups.setdefault(
            key,
            {
                "consignee": row["consignee"],
                "currency": row["currency"],
                "route": row["route"],
                "route_basis": row["route_basis"],
                "handling": row["handling"],
                "companies": set(),
                "dates": [],
                "count": 0,
                "amount": Decimal(0),
                "batched": 0,
                "pending": 0,
                "issues": 0,
            },
        )
        group["count"] += 1
        if row["export_company"]:
            group["companies"].add(row["export_company"])
        if row["export_date"]:
            group["dates"].append(row["export_date"])
        if row["amount"] is None:
            group["issues"] += 1
        else:
            group["amount"] += row["amount"]
        if row["batch_no"]:
            group["batched"] += 1
        elif row["handling"] == "batch" and not row["blocked"]:
            group["pending"] += 1
    ordered = sorted(groups.values(), key=lambda g: (-g["amount"], g["consignee"].casefold(), g["currency"]))
    return [
        ConsigneeTotal(
            consignee=group["consignee"],
            currency=group["currency"],
            route=group["route"],
            routeLabel=ROUTE_LABELS[group["route"]],
            routeBasis=group["route_basis"],
            handling=group["handling"],
            handlingLabel=HANDLING_LABELS[group["handling"]],
            exportCompanies=sorted(group["companies"]),
            count=group["count"],
            firstExportDate=str(min(group["dates"])) if group["dates"] else "",
            lastExportDate=str(max(group["dates"])) if group["dates"] else "",
            amount=str(money(group["amount"])),
            batchedCount=group["batched"],
            pendingCount=group["pending"],
            issueCount=group["issues"],
        )
        for group in ordered
    ]
