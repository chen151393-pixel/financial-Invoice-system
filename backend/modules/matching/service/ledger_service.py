"""失效、承接及绝对合计；不把任务缓存作为台账来源。"""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from backend.modules.invoice.public import lock_invoice
from backend.modules.review.public import basis_versions, current_bases
from backend.modules.task.public import open_lines, related_line_ids

from ..dao import allocation_dao, ledger_dao
from ..public import AllocationChanged, LineReceipt


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def effective_basis(row):
    history = row["verification_history"] or []
    return next(
        (h["purchaseBasisId"] for h in reversed(history) if h.get("purchaseBasisId")),
        row["purchase_basis_id"],
    )


def effective_invoice(row):
    history = row["verification_history"] or []
    return next(
        (h["invoiceVersionId"] for h in reversed(history) if h.get("invoiceVersionId")),
        row["invoice_version_id"],
    )


def history_entry(row, action, actor, basis_id, invoice_version_id, stamp):
    return {
        "action": action,
        "actor": actor,
        "at": stamp.isoformat(),
        "purchaseBasisId": basis_id,
        "invoiceVersionId": invoice_version_id,
        "quantity": str(row["quantity"]),
        "purchaseQuantity": str(row.get("purchase_quantity")),
        "amount": str(row["amount"]),
        "issues": row.get("verification_issues") or [],
        "note": row.get("review_note"),
        "conversionEvidence": row.get("conversion_evidence"),
        "conversionNumerator": str(row.get("conversion_numerator")),
        "conversionDenominator": str(row.get("conversion_denominator")),
    }


def publish(connection, line_ids, events, actor, reason):
    bases = current_bases(connection, line_ids)
    receipts = []
    for line_id in sorted(set(line_ids)):
        basis = bases.get(line_id)
        rows = [
            r for r in ledger_dao.by_lines(connection, [line_id]) if r["status"] in ("confirmed", "cancelled")
        ]
        active = [r for r in rows if r["status"] == "confirmed"]
        valid = [
            r
            for r in active
            if r["verification_status"] == "valid"
            and basis
            and basis["allowed"]
            and effective_basis(r) == basis["id"]
        ]
        pending = [r for r in active if r not in valid]
        fields = (
            "id",
            "invoice_version_id",
            "purchase_basis_id",
            "quantity",
            "purchase_quantity",
            "amount",
            "status",
            "verification_status",
            "verification_issues",
            "verification_history",
        )
        digest = hashlib.sha256(
            json.dumps([{k: r[k] for k in fields} for r in rows], sort_keys=True, default=str).encode()
        ).hexdigest()
        receipts.append(
            LineReceipt(
                purchase_line_id=line_id,
                quantity=sum((r["purchase_quantity"] or Decimal(0) for r in valid), Decimal(0)),
                amount=sum((r["amount"] for r in valid), Decimal(0)),
                purchase_basis_id=basis["id"] if basis else None,
                ledger_sha256=digest,
                requires_review=bool(pending) or not basis or not basis["allowed"],
                pending_quantity=sum((r["purchase_quantity"] or Decimal(0) for r in pending), Decimal(0)),
                pending_amount=sum((r["amount"] for r in pending), Decimal(0)),
            )
        )
    events.publish(connection, AllocationChanged(tuple(receipts), actor, reason))


def prepare(connection, line_ids, invoice_ids):
    current_bases(connection, line_ids, lock=True)
    open_lines(connection, line_ids, lock=True)
    for invoice_id in sorted(set(invoice_ids)):
        lock_invoice(connection, invoice_id)
    ledger_dao.by_lines(connection, line_ids, lock=True)


def invalidate(connection, rows, issue, invalid=False):
    stamp = now()
    for row in rows:
        if row["status"] == "proposed":
            allocation_dao.update_status(
                connection,
                row["id"],
                {
                    "status": "rejected",
                    "review_note": issue["reason"],
                    "reviewed_by": "system",
                    "reviewed_at": stamp,
                },
                stamp,
            )
        elif row["status"] == "confirmed":
            issues = [
                i
                for i in row["verification_issues"] or []
                if not isinstance(i, dict) or i.get("kind") != issue["kind"]
            ] + [issue]
            history = (row["verification_history"] or []) + [
                {"action": "invalidated", "at": stamp.isoformat(), "issue": issue}
            ]
            allocation_dao.update_status(
                connection,
                row["id"],
                {
                    "verification_status": "invalid" if invalid else "needs_review",
                    "verification_issues": issues,
                    "verification_history": history,
                },
                stamp,
            )


def on_basis_invalidated(connection, event, *, events):
    rows = ledger_dao.by_lines(connection, event.purchase_line_ids)
    prepare(connection, event.purchase_line_ids, [r["invoice_id"] for r in rows])
    invalidate(connection, rows, {"kind": "basis", "reason": event.reason})
    publish(connection, event.purchase_line_ids, events, "system", event.reason)


def on_invoice_changing(connection, event):
    rows = allocation_dao.by_invoices(connection, event.invoice_ids)
    prepare(connection, sorted({r["purchase_line_id"] for r in rows}), event.invoice_ids)


def on_invoice_changed(connection, event, *, events):
    rows = allocation_dao.by_invoices(connection, [event.invoice_id])
    invalidate(
        connection,
        rows,
        {"kind": "invoice", "reason": "发票版本变化，请核实原分配", "versionId": event.version_id},
        event.status in ("void", "red_offset"),
    )
    publish(connection, [r["purchase_line_id"] for r in rows], events, "system", "发票版本变化，收票进度重算")


def on_review_approved(connection, event, *, events):
    ids = related_line_ids(connection, [line.purchase_line_id for line in event.lines])
    rows = ledger_dao.by_lines(connection, ids)
    prepare(connection, ids, [r["invoice_id"] for r in rows])
    bases = current_bases(connection, ids)
    previous = basis_versions(connection, [effective_basis(r) for r in rows if effective_basis(r)])
    stamp = now()
    for row in rows:
        basis = bases.get(row["purchase_line_id"])
        old = previous.get(effective_basis(row))
        if row["status"] == "proposed" and (not basis or row["purchase_basis_id"] != basis["id"]):
            invalidate(connection, [row], {"kind": "basis", "reason": "开票依据换版，请重新生成建议"})
        if row["status"] != "confirmed" or not basis or not old or not basis["allowed"]:
            continue
        compatible = all(
            old[k] == basis[k]
            for k in ("ns_account", "purchase_line_id", "supplier_id", "company_id", "currency", "unit")
        )
        if compatible and row["purchase_quantity"] is not None:
            if effective_basis(row) == basis["id"] and not any(
                isinstance(i, dict) and i.get("kind") == "basis" for i in row["verification_issues"] or []
            ):
                continue
            issues = [
                i
                for i in row["verification_issues"] or []
                if not isinstance(i, dict) or i.get("kind") != "basis"
            ]
            history = (row["verification_history"] or []) + [
                history_entry(
                    row, "basis_carried", event.approved_by, basis["id"], effective_invoice(row), stamp
                )
            ]
            allocation_dao.update_status(
                connection,
                row["id"],
                {
                    "verification_status": (
                        "invalid" if row["verification_status"] == "invalid" else "needs_review"
                    )
                    if issues
                    else "valid",
                    "verification_issues": issues,
                    "verification_history": history,
                },
                stamp,
            )
        else:
            invalidate(
                connection, [row], {"kind": "basis", "reason": "新旧开票口径不兼容，须核实或取消后重新分配"}
            )
    publish(connection, ids, events, event.approved_by, "审核依据换版，按分配台账重算收票")
