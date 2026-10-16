"""冻结全局开票依据与来源失效传播，全部复用发布方事务。"""

import hashlib
import json
from datetime import datetime, timezone

from backend.core.errors import ApiError
from backend.modules.source.public import purchase_lines

from ..dao import purchase_basis_dao
from ..public import PurchaseBasisInvalidated


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def freeze(connection, content, rows, body, review_id, actor, now):
    ids = [row["purchase_line_id"] for row in rows]
    sources = purchase_lines(connection, ids, lock=True)
    current = purchase_basis_dao.current(connection, ids, lock=True)
    evidence = {int(item.purchaseOrderId): item for item in body.currencyEvidence}
    orders = {r["purchase_order_id"] for r in rows}
    if len(evidence) != len(body.currencyEvidence) or set(evidence) - orders:
        raise ApiError(422, "币种证据的子采购单重复或不属于本次审核")
    for row in rows:
        source = sources[row["purchase_line_id"]]
        old = current.get(row["purchase_line_id"])
        currency, currency_source, proof = _currency(
            source, old, evidence.get(row["purchase_order_id"]), actor, now
        )
        values = {
            k: row[k]
            for k in (
                "purchase_order_id",
                "purchase_line_id",
                "supplier_id",
                "company_id",
                "quantity",
                "unit",
                "amount",
            )
        }
        values.update(currency=currency, currency_source=currency_source, source_sha256=source["digest"])
        basis_hash = _digest(
            {**values, "proof": {k: proof[k] for k in ("reference", "note")} if proof else None}
        )
        if old and old["status"] == "active" and old["basis_sha256"] == basis_hash:
            basis_id = old["id"]
        else:
            if old:
                purchase_basis_dao.set_status(connection, [old["id"]], "superseded", now)
            values.update(
                ns_account=source["ns_account"],
                revision=purchase_basis_dao.next_revision(connection, row["purchase_line_id"]),
                status="active",
                basis_sha256=basis_hash,
                source_refs=source["source_refs"],
                currency_evidence=proof,
                origin_review_id=review_id,
                approved_by=actor,
                approved_at=now,
            )
            basis_id = purchase_basis_dao.insert_basis(connection, values, now)
        row.update(currency=currency, purchase_basis_id=basis_id)
    return rows


def on_source_changed(connection, event, *, events):
    sources = purchase_lines(connection, event.purchase_line_ids, lock=True)
    current = purchase_basis_dao.current(connection, event.purchase_line_ids, lock=True)
    affected = [
        basis
        for line_id, basis in current.items()
        if basis["status"] == "active"
        and (
            line_id not in sources
            or not sources[line_id]["active"]
            or basis["source_sha256"] != sources[line_id]["digest"]
        )
    ]
    if affected:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        purchase_basis_dao.set_status(connection, [b["id"] for b in affected], "review_required", now)
        events.publish(
            connection, PurchaseBasisInvalidated(tuple(b["purchase_line_id"] for b in affected), event.reason)
        )


def same_evidence(connection, rows, body):
    """重复提交相同证据不追加报关审核；缺币种本身仍可保留待核实展示。"""
    current = purchase_basis_dao.current(connection, [r["purchase_line_id"] for r in rows])
    evidence = {int(item.purchaseOrderId): item for item in body.currencyEvidence}
    if len(evidence) != len(body.currencyEvidence) or set(evidence) - {r["purchase_order_id"] for r in rows}:
        return False
    for row in rows:
        basis = current.get(row["purchase_line_id"])
        if not basis or basis["status"] != "active":
            return False
        manual = evidence.get(row["purchase_order_id"])
        if manual:
            proof = basis["currency_evidence"] or {}
            if (
                basis["currency"] != manual.currency
                or proof.get("reference") != manual.reference.strip()
                or proof.get("note") != manual.note.strip()
            ):
                return False
    return True


def _currency(source, old, manual, actor, now):
    currency, currency_source, proof = source["currency"], source["currency_source"], None
    if manual:
        if currency or source["parent_relation_status"] == "unknown":
            raise ApiError(409, "已有来源币种或母单尚未读取，不能用人工币种覆盖，请先核实来源")
        currency, currency_source = manual.currency, "manual_verified"
        proof = {
            "reference": manual.reference.strip(),
            "note": manual.note.strip(),
            "actor": actor,
            "at": now.isoformat(),
            "sourceSha256": source["digest"],
        }
    elif old and old["currency_source"] == "manual_verified" and old["source_sha256"] == source["digest"]:
        currency, currency_source, proof = (
            old["currency"],
            old["currency_source"],
            old["currency_evidence"],
        )
    return currency, currency_source, proof
