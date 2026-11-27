"""收汇总览：统一应收、客户实收、未收差额；只读，不改变订单或结汇状态。

香港客户实收只取有效香港批次登记的首次到账；不把香港公司汇回境内的银行流水再次计入。
直接收汇实收与总账共用银行收汇来源和实际客户归属，不叠加旧直接收汇批次。
"""

import math
from decimal import Decimal

from backend.core.errors import ApiError

from ..dao import bank_receipt_dao, batch_dao
from ..policy import overview_insight_policy as insights
from ..policy.amount_policy import money
from ..policy.consignee_policy import consignee_key
from ..policy.route_policy import DIRECT, HK_TRANSIT, ROUTE_LABELS
from ..vo.ledger_vo import LedgerSkipped
from ..vo.overview_vo import OverviewCustomer, OverviewList, OverviewRoute, OverviewTotal


def _group(groups, route, consignee, currency):
    key = (route, consignee_key(consignee), currency)
    return groups.setdefault(
        key,
        {
            "route": route,
            "consignee": consignee,
            "currency": currency,
            "count": 0,
            "declared": Decimal(0),
            "received": Decimal(0),
            "fee": Decimal(0),
        },
    )


def _amounts(group):
    return {
        "declaredTotal": str(money(group["declared"])),
        "receivedTotal": str(money(group["received"])),
        "outstanding": str(money(group["declared"] - group["received"])),
        "receivedFee": str(money(group["fee"])),
    }


def _totals(groups):
    """每个币种固定返回两条路径；没有记录的路径为零，不跨币种加总。"""
    totals = []
    for currency in sorted({group["currency"] for group in groups}):
        routes, combined = [], {"declared": Decimal(0), "received": Decimal(0), "fee": Decimal(0)}
        for route in (HK_TRANSIT, DIRECT):
            values = {
                field: sum(
                    (g[field] for g in groups if g["currency"] == currency and g["route"] == route),
                    Decimal(0),
                )
                for field in combined
            }
            routes.append(OverviewRoute(route=route, routeLabel=ROUTE_LABELS[route], **_amounts(values)))
            for field in combined:
                combined[field] += values[field]
        totals.append(OverviewTotal(currency=currency, routes=routes, **_amounts(combined)))
    return totals


class OverviewService:
    def __init__(self, engine, candidates, receivables=None):
        self.engine = engine
        self.candidates = candidates
        self.receivables = receivables

    def query(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            display = self.candidates.display_names(connection)
            declarations = self.candidates.load(connection, limit=None)
            receipts = bank_receipt_dao.all_receipts(connection)
            batches = batch_dao.customer_receipts(connection)
            snapshot, as_of = [], ""
            if self.receivables is not None:
                snapshot, _, _, heads, items, today = self.receivables.snapshot(connection)
                as_of = str(today)
                wanted = consignee_key(body.consignee)
                snapshot = [
                    row
                    for row in snapshot
                    if (not wanted or wanted in consignee_key(row["consignee"]))
                    and (not body.currency or body.currency.upper() == row["currency"])
                ]
                # 仅核对当前范围内待办香港批次的资料，不读取直接收汇留存文件。
                pending_docs = [row for row in snapshot if row["stage"] == "collected"]
                self.receivables._documents(connection, pending_docs, heads, items)

        groups, skipped = {}, []
        wanted = consignee_key(body.consignee)

        def matches(name, currency):
            return (not wanted or wanted in consignee_key(name)) and (
                not body.currency or body.currency.upper() == currency
            )

        for row in declarations:
            reason = row["currency_issue"] or (
                "" if consignee_key(row["consignee"]) else "海关回执没有境外收货人"
            )
            if row["amount"] is None and not reason:
                reason = "海关回执没有可用金额"
            if reason:
                if matches(row["consignee"], row["currency"]):
                    skipped.append(
                        LedgerSkipped(
                            declarationNo=row["declaration_no"],
                            consignee=display.display_name(row["consignee"]),
                            reason=reason,
                        )
                    )
                continue
            # 已建批次的报关单仍属于应收；不能把“未建批次”当成未收金额。
            group = _group(groups, row["route"], row["consignee"], row["currency"])
            group["declared"] += row["amount"]
            group["count"] += 1

        for row in batches:
            group = _group(groups, HK_TRANSIT, row["consignee"], row["currency"])
            group["received"] += row["received_amount"]
            group["fee"] += row["received_fee"]

        for row in receipts:
            if self.candidates.route(row["customer_name"])[0] != DIRECT:
                continue
            group = _group(groups, DIRECT, row["customer_name"], row["currency"])
            group["received"] += row["amount"]

        currencies = sorted({group["currency"] for group in groups.values()})
        selected = [g for g in groups.values() if matches(g["consignee"], g["currency"])]
        selected.sort(
            key=lambda g: (g["currency"], -(g["declared"] - g["received"]), consignee_key(g["consignee"]))
        )
        total = len(selected)
        page = min(body.page, max(1, math.ceil(total / body.pageSize)))
        shown = selected[(page - 1) * body.pageSize : page * body.pageSize]
        totals = _totals(selected)
        if self.receivables is not None:
            for total_row in totals:
                members = [row for row in snapshot if row["usable"] and row["currency"] == total_row.currency]
                settled = [row for row in members if row["stage"] == "settled"]
                total_row.settledAmount = str(money(sum((row["amount"] for row in settled), Decimal(0))))
                total_row.settledCount = len(settled)
                total_row.declarationCount = len(members)
        return OverviewList(
            items=[
                OverviewCustomer(
                    consignee=display.display_name(group["consignee"]),
                    currency=group["currency"],
                    route=group["route"],
                    routeLabel=ROUTE_LABELS[group["route"]],
                    declarationCount=group["count"],
                    **_amounts(group),
                    **insights.customer_fields(group, snapshot),
                )
                for group in shown
            ],
            total=total,
            page=page,
            pageSize=body.pageSize,
            totals=totals,
            insights=insights.describe(snapshot, selected, body.consignee)
            if self.receivables is not None
            else [],
            asOf=as_of,
            currencies=currencies,
            skipped=skipped,
        )
