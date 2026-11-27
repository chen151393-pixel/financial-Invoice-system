"""报关单详情只读规则：复用逐单已收结果，解释银行流水的先后冲抵。"""

from datetime import date
from decimal import Decimal

from . import receivable_policy as rules
from .amount_policy import money


def text_amount(value):
    return str(money(value))


def direct_evidence(row, rows, receipts):
    """相同收货人×抬头×币种；全部历史先推算，再提供每笔流水的解释，不写分配关系。"""
    key = rules.direct_key(row["consignee"], row["currency"], row["export_company"])
    same = [
        r
        for r in rows
        if r["route"] == "direct"
        and r["usable"]
        and rules.direct_key(r["consignee"], r["currency"], r["export_company"]) == key
    ]
    same.sort(key=lambda r: (r["export_date"] or date.min, r["declaration_no"]))
    banks = [
        r
        for r in receipts
        if rules.direct_key(r["customer_key"], r["currency"], r["receiving_company"]) == key
    ]
    banks.sort(key=lambda r: (r["receipt_date"] or date.min, r["id"]))
    remaining = [Decimal(r["amount"]) for r in banks]
    result, index = [], 0
    for declaration in same:
        need = declaration["received"]
        used = []
        while need > 0 and index < len(banks):
            if remaining[index] <= 0:
                index += 1
                continue
            bank = banks[index]
            value = min(need, remaining[index])
            used.append(
                dict(
                    receiptId=bank["id"],
                    date=str(bank["receipt_date"] or ""),
                    reference=bank["reference"] or "",
                    receiptAmount=text_amount(bank["amount"]),
                    appliedAmount=text_amount(value),
                    payer=bank["payer_name"],
                    thirdParty=bank["payer_key"] != bank["customer_key"],
                )
            )
            need -= value
            remaining[index] -= value
        result.append(
            dict(
                declarationNo=declaration["declaration_no"],
                exportDate=str(declaration["export_date"] or ""),
                amount=text_amount(declaration["amount"]),
                receivedAmount=text_amount(declaration["received"]),
                outstandingAmount=text_amount(declaration["outstanding"]),
                current=declaration["declaration_no"] == row["declaration_no"],
                receipts=used,
            )
        )
    balance = sum((r["amount"] for r in same), Decimal(0)) - sum(
        (Decimal(r["amount"]) for r in banks), Decimal(0)
    )
    return result, text_amount(balance)


def steps(row, state):
    def step(key, label, description, status, percent=None):
        return dict(
            key=key,
            label=label,
            description=description,
            state=status,
            percent=(100 if status == "done" else 0) if percent is None else percent,
        )

    exported = step(
        "export", "报关", str(row["export_date"] or "出口日期待补"), "done" if row["usable"] else "current"
    )
    if row["route"] == "direct":
        width, percent = rules.received_percent(row["received"], row["amount"] if row["usable"] else None)
        return [
            exported,
            step(
                "receipt",
                f"收汇 {percent}",
                f"已收 {text_amount(row['received'])} · 未收 {text_amount(row['outstanding'])}",
                "done" if row["stage"] == rules.SETTLED else "current",
                width,
            ),
            step(
                "settled",
                "已结汇" if row["stage"] == rules.SETTLED else "待收齐结汇",
                "收齐自动结汇，资料留存不影响结汇",
                "done" if row["stage"] == rules.SETTLED else "waiting",
            ),
        ]
    batch = row["batch"]
    status = batch["status"] if batch else ""
    ready = status in ("documents_ready", "settled")
    complete = not state["issues"] if state else False
    return [
        exported,
        step(
            "receipt",
            "香港到账",
            str(batch["received_on"] or "") if batch else "待登记回款",
            "done" if batch else "current",
        ),
        step(
            "documents",
            "资料齐全",
            "资料已齐" if complete else "提单、合同待补齐",
            "done" if complete else "current" if batch and not ready else "waiting",
        ),
        step(
            "sent",
            "资料已出",
            "已确认" if ready else "待确认",
            "done" if ready else "current" if complete else "waiting",
        ),
        step(
            "settled",
            "汇回结汇",
            "已完成" if status == "settled" else "待汇回境内核对",
            "done" if status == "settled" else "current" if ready else "waiting",
        ),
    ]
