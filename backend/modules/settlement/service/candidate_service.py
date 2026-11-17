"""可结汇报关单：读取海关回执金额，判定回款路径，标出已被批次占用的报关单，并按金额推荐组合。"""

from collections import defaultdict
from decimal import Decimal

from backend.core.errors import ApiError
from backend.modules.review.public import settlement_declarations
from backend.modules.source.public import declaration_refs_by_number

from ..dao import batch_dao, batch_item_dao
from ..policy.amount_policy import money, suggest_combination
from ..policy.route_policy import ROUTE_LABELS, hk_consignee_keys, route_of
from ..vo.batch_vo import Candidate, CandidateList, RouteTotal

CANDIDATE_LIMIT = 500


def record_numbers(connection, numbers):
    """真实报关单号 → NS CD 编号；重号时以顿号列出全部。"""
    refs = declaration_refs_by_number(connection, numbers)
    return {number: "、".join(sorted(h["record_no"] or "" for h in heads)) for number, heads in refs.items()}


def describe(rows, record_nos, occupied, batch_nos, hk_keys):
    """海关回执行 → 候选报关单 dict（含路径与不可选原因）。"""
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
                "blocked": blocked,
                "batch_no": "" if batch_id is None else str(batch_nos.get(batch_id, batch_id)),
                "record_no": record_nos.get(row["declaration_no"], ""),
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

    def load(self, connection, *, numbers=None, consignee=""):
        """读取并判定候选报关单；供建批次在事务中复用同一套规则。"""
        rows = settlement_declarations(
            connection, numbers=numbers, consignee=consignee, limit=CANDIDATE_LIMIT
        )
        numbers_found = [row["declaration_no"] for row in rows]
        occupied = batch_item_dao.active_by_numbers(connection, numbers_found)
        batch_nos = {}
        if occupied:
            _, heads = batch_dao.page(connection, {"ids": sorted(set(occupied.values()))}, 0, len(occupied))
            batch_nos = {head["id"]: head["batch_no"] for head in heads}
        return describe(rows, record_numbers(connection, numbers_found), occupied, batch_nos, self.hk_keys)

    def query(self, body):
        self._require_engine()
        with self.engine.connect() as connection:
            rows = self.load(connection, consignee=body.consignee)
        if body.declarationNo:
            rows = [row for row in rows if body.declarationNo in row["declaration_no"]]
        if body.route != "all":
            rows = [row for row in rows if row["route"] == body.route]
        open_rows = [row for row in rows if not row["blocked"]]
        suggestion, note = None, ""
        if body.targetAmount:
            groups = {(row["consignee"], row["currency"]) for row in open_rows}
            if len(groups) != 1:
                note = "请先按境外收货人筛选到同一收货人、同一币种，再推荐组合"
            else:
                suggestion = suggest_combination(
                    [(row["declaration_no"], row["amount"]) for row in open_rows], Decimal(body.targetAmount)
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
                    exportDate="" if row["export_date"] is None else str(row["export_date"]),
                    salesOrders=row["sales_orders"],
                    currency=row["currency"],
                    amount="" if row["amount"] is None else str(money(row["amount"])),
                    route=row["route"],
                    routeLabel=ROUTE_LABELS[row["route"]],
                    routeBasis=row["route_basis"],
                    blockedReason=row["blocked"],
                    batchNo=row["batch_no"],
                )
                for row in rows
            ],
            unsettled=_route_totals(open_rows),
            suggestion=suggestion,
            suggestionNote=note,
        )


def _route_totals(rows):
    """未进入批次的报关单金额，按路径与币种汇总（已报关未结汇）。"""
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
