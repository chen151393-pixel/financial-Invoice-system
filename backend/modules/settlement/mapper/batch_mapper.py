"""结汇批次行 → VO 的纯转换；金额核对结果由调用方按规则计算后传入。"""

from ..policy.amount_policy import balance_check, money
from ..policy.batch_state_policy import actions, status_label
from ..policy.route_policy import HK_TRANSIT, ROUTE_LABELS
from ..vo.batch_vo import Balance, BatchActions, BatchDetail, BatchItem, BatchSummary


def text(value):
    return "" if value is None else str(value)


def amount(value):
    return "" if value is None else str(money(value))


def stamp(value):
    return "" if value is None else value.isoformat(timespec="seconds") + "Z"


def balances(batch, fee_alert):
    """到账核对；香港中转登记汇回后追加汇回核对。"""
    received = balance_check(
        batch["declared_total"], batch["received_amount"], batch["received_fee"], fee_alert
    )
    hk = batch["route"] == HK_TRANSIT
    result = [
        ("received", "香港到账" if hk else "到账", batch["received_amount"], batch["received_fee"], received)
    ]
    remitted = None
    if hk and batch["remitted_amount"] is not None:
        remitted = balance_check(
            batch["declared_total"], batch["remitted_amount"], batch["remitted_fee"], fee_alert
        )
        result.append(("remitted", "汇回境内", batch["remitted_amount"], batch["remitted_fee"], remitted))
    views = [
        Balance(
            stage=stage,
            label=label,
            arrived=amount(arrived),
            fee=amount(fee),
            difference=str(check["difference"]),
            balanced=check["balanced"],
            warnings=check["warnings"],
        )
        for stage, label, arrived, fee, check in result
    ]
    return views, received["balanced"], (remitted["balanced"] if remitted else None)


def summary_fields(batch, count, fee_alert, documents_issue=""):
    views, received_ok, remitted_ok = balances(batch, fee_alert)
    allowed = actions(batch, received_ok, remitted_ok)
    if documents_issue and allowed["documentsReady"]["allowed"]:
        # 金额已对平但资料未齐：给出资料缺项
        allowed["documentsReady"] = {"allowed": False, "reason": documents_issue}
    return {
        "id": batch["id"],
        "batchNo": text(batch["batch_no"]),
        "route": batch["route"],
        "routeLabel": ROUTE_LABELS[batch["route"]],
        "status": batch["status"],
        "statusLabel": status_label(batch["route"], batch["status"]),
        "consignee": batch["consignee"],
        "currency": batch["currency"],
        "declaredTotal": amount(batch["declared_total"]),
        "receivedOn": text(batch["received_on"]),
        "receivedAmount": amount(batch["received_amount"]),
        "receivedFee": amount(batch["received_fee"]),
        "remittedOn": text(batch["remitted_on"]),
        "remittedAmount": amount(batch["remitted_amount"]),
        "remittedFee": amount(batch["remitted_fee"]),
        "declarationCount": count,
        "balances": views,
        "actions": BatchActions(**allowed),
    }


def summary(batch, count, fee_alert):
    return BatchSummary(**summary_fields(batch, count, fee_alert))


def detail(batch, items, fee_alert, documents_issue=""):
    return BatchDetail(
        **summary_fields(batch, len(items), fee_alert, documents_issue),
        payer=text(batch["payer"]),
        receivingAccount=text(batch["receiving_account"]),
        receivedReference=text(batch["received_reference"]),
        remittedReference=text(batch["remitted_reference"]),
        note=text(batch["note"]),
        createdBy=batch["created_by"],
        createdAt=stamp(batch["created_at"]),
        documentsReadyBy=text(batch["documents_ready_by"]),
        documentsReadyAt=stamp(batch["documents_ready_at"]),
        settledBy=text(batch["settled_by"]),
        settledAt=stamp(batch["settled_at"]),
        cancelledBy=text(batch["cancelled_by"]),
        cancelReason=text(batch["cancel_reason"]),
        items=[
            BatchItem(
                declarationNo=item["declaration_no"],
                recordNo=text(item["record_no"]),
                salesOrders=text(item["sales_orders"]),
                consignee=item["consignee"],
                exportDate=text(item["export_date"]),
                currency=item["currency"],
                amount=amount(item["declared_amount"]),
            )
            for item in items
        ],
    )
