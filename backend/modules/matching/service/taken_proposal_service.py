"""一张子采购单只由一张发票开具（2026-11-10）：子采购明细被某张发票整单通过后，其他发票上占用它们的待审核建议自动失效。

- 整单通过时（group_view_service.approve_rows）在同一事务内处理，其他发票的旧建议整组驳回并留痕；
- 页面“重新生成建议”（proposal_service.generate refresh=True）时再检查一次，清理部署前遗留的旧建议。
驳回不改已通过分配，不调用 NS；被驳回的发票可重新生成建议或人工关联其他子采购单。
"""

from backend.modules.invoice.public import read_invoices

from ..dao import allocation_dao
from ..policy.allocation_policy import SYSTEM


def _group(row):
    return ((row["checks"] or {}).get("group") or {}).get("id")


def _note(numbers):
    return (
        f"子采购单已由发票 {'、'.join(sorted(numbers))} 整单关联，一张子采购单只能由一张发票开具；"
        "本建议自动失效，可重新生成建议或人工关联其他子采购单"
    )


def _reject_groups(connection, stale, owners, now):
    """stale：需失效的待审核分配；同组其余待审核记录一并驳回，保持整组一致。返回驳回条数。"""
    if not stale:
        return 0
    keys = {(row["invoice_id"], _group(row) or f"row:{row['id']}") for row in stale}
    numbers = {
        invoice["id"]: invoice["invoice_no"]
        for invoice in read_invoices(connection, sorted(set().union(*owners.values())))
    }
    rejected = 0
    for row in allocation_dao.by_invoices(connection, sorted({invoice_id for invoice_id, _ in keys})):
        if row["status"] != "proposed" or (row["invoice_id"], _group(row) or f"row:{row['id']}") not in keys:
            continue
        owner_numbers = {
            numbers.get(owner, str(owner))
            for line_row in stale
            if line_row["invoice_id"] == row["invoice_id"]
            for owner in owners.get(line_row["purchase_line_id"], ())
        }
        allocation_dao.update_status(
            connection,
            row["id"],
            {
                "status": "rejected",
                "reviewed_by": SYSTEM,
                "reviewed_at": now,
                "review_note": _note(owner_numbers),
            },
            now,
        )
        rejected += 1
    return rejected


def retire_after_confirm(connection, invoice_id, line_ids, now):
    """发票 invoice_id 整单通过 line_ids 后，其他发票上占用这些明细的待审核建议整组失效。"""
    stale = allocation_dao.proposed_by_purchase_lines(connection, line_ids, exclude_invoice_id=invoice_id)
    return _reject_groups(connection, stale, {line_id: {invoice_id} for line_id in line_ids}, now)


def retire_taken(connection, invoice_ids, now):
    """重新生成前：这些发票的待审核建议中，子采购明细已被其他发票通过的整组失效。"""
    proposed = [
        row for row in allocation_dao.by_invoices(connection, invoice_ids) if row["status"] == "proposed"
    ]
    confirmed = allocation_dao.confirmed_invoices_by_lines(
        connection, [row["purchase_line_id"] for row in proposed]
    )
    # 只看其他发票的通过记录；本票自己的通过记录不算占用
    owners = {}
    stale = []
    for row in proposed:
        others = confirmed.get(row["purchase_line_id"], set()) - {row["invoice_id"]}
        if others:
            owners[row["purchase_line_id"]] = others
            stale.append(row)
    return _reject_groups(connection, stale, owners, now)
