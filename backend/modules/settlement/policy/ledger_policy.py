"""直接收汇明细（总账）规则（纯函数）。

业务规则（2026-11-18 确认）：非香港中转的报关单不建批次，按境外收货人记流水账——
出口（报关单成交总价）增加应收，收汇（银行收汇明细）减少应收，按对账期间汇总期初与期末差额；
余额为负表示超收。同一天既有出口又有收汇时先记出口。金额一律 Decimal，不使用浮点。
"""

from datetime import date
from decimal import Decimal

from backend.core.names import normalize_name

EXPORT = "export"
RECEIPT = "receipt"
KIND_LABELS = {EXPORT: "出口", RECEIPT: "收汇"}
STATUS_LABELS = {"outstanding": "有未收", "settled": "已收齐", "overpaid": "超收"}
# 同一天先出口后收汇
_KIND_ORDER = {EXPORT: 0, RECEIPT: 1}


def balance_status(balance):
    if balance > 0:
        return "outstanding"
    return "overpaid" if balance < 0 else "settled"


def export_entry(row):
    """候选报关单（直接收汇、金额有效）→ 出口流水。"""
    return {
        "kind": EXPORT,
        "key": normalize_name(row["consignee"]),
        "name": row["consignee"],
        "currency": row["currency"],
        "date": row["export_date"],
        "amount": Decimal(row["amount"]),
        "company": row.get("export_company") or "",
        "source_no": row["declaration_no"],
        "payer": "",
        "third_party": False,
        "order": row["declaration_no"],
    }


def receipt_entry(row):
    """银行收汇记录 → 收汇流水，按实际客户归属。"""
    return {
        "kind": RECEIPT,
        "key": row["customer_key"],
        "name": row["customer_name"],
        "currency": row["currency"],
        "date": row["receipt_date"],
        "amount": Decimal(row["amount"]),
        "company": row["receiving_company"],
        "source_no": row["reference"] or "",
        "payer": row["payer_name"],
        "third_party": row["payer_key"] != row["customer_key"],
        "order": f"{row.get('receipt_time') or '00:00:00'}|{row['id']:020d}",
    }


def build_groups(entries, *, start=None, end=None, by_recipient=False):
    """流水按境外收货人、币种分组，可进一步按收款抬头拆分。

    返回 [{key, consignee, currency, export_total, receipt_total, balance, status, entries}]，
    按收货人名称、币种排序；缺出口日期的出口排在最前。
    """
    grouped = {}
    for entry in entries:
        if end and (entry["date"] is None or entry["date"] > end):
            continue
        recipient = normalize_name(entry["company"]) if by_recipient else ""
        grouped.setdefault((entry["key"], entry["currency"], recipient), []).append(entry)
    groups = []
    for (key, currency, _), rows in grouped.items():
        rows.sort(key=lambda e: (e["date"] or date.min, _KIND_ORDER[e["kind"]], e["order"]))
        opening = Decimal(0)
        export_total = Decimal(0)
        receipt_total = Decimal(0)
        lines = []
        for row in rows:
            if start and row["date"] < start:
                opening += row["amount"] if row["kind"] == EXPORT else -row["amount"]
                continue
            if row["kind"] == EXPORT:
                export_total += row["amount"]
            else:
                receipt_total += row["amount"]
            lines.append({**row, "balance": opening + export_total - receipt_total})
        if not lines and opening == 0:
            continue
        balance = lines[-1]["balance"] if lines else opening
        # 展示名称优先取报关单上的境外收货人，没有出口时取收汇表格的实际客户
        named = next((row for row in rows if row["kind"] == EXPORT), rows[0])
        recipient = next((row["company"] for row in rows if row["kind"] == RECEIPT), named["company"])
        groups.append(
            {
                "key": key,
                "consignee": named["name"],
                "receiving_company": recipient if by_recipient else "",
                "currency": currency,
                "opening_balance": opening,
                "export_total": export_total,
                "receipt_total": receipt_total,
                "balance": balance,
                "status": balance_status(balance),
                "entries": lines,
            }
        )
    groups.sort(
        key=lambda group: (group["consignee"].casefold(), group["currency"], group["receiving_company"])
    )
    return groups


def currency_totals(groups):
    """各币种合计：[{currency, export_total, receipt_total, balance, outstanding, overpaid}]。

    outstanding 为余额为正的各组之和，overpaid 为余额为负的各组之和（负数）。
    """
    totals = {}
    for group in groups:
        total = totals.setdefault(
            group["currency"],
            {
                "currency": group["currency"],
                "opening_balance": Decimal(0),
                "export_total": Decimal(0),
                "receipt_total": Decimal(0),
                "balance": Decimal(0),
                "outstanding": Decimal(0),
                "overpaid": Decimal(0),
            },
        )
        total["export_total"] += group["export_total"]
        total["opening_balance"] += group["opening_balance"]
        total["receipt_total"] += group["receipt_total"]
        total["balance"] += group["balance"]
        total["outstanding" if group["balance"] > 0 else "overpaid"] += group["balance"]
    return [totals[currency] for currency in sorted(totals)]
