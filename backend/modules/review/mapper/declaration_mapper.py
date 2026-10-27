"""source 报关单内容 → 财务核对展示；审核冻结行。纯转换，不查询数据库。"""

import hashlib
import json
from collections import defaultdict
from datetime import UTC
from decimal import Decimal

from backend.modules.source.public import unit_label

from ..policy.auto_review_policy import auto_review_reasons, margin_alert
from ..policy.margin_policy import declared_margin
from ..policy.purchase_display_policy import group_purchase_lines
from ..policy.review_policy import CHANGED_WARNING, STATUS_LABELS
from ..public import ApprovedLine
from ..vo.review_vo import AutoReview, CustomsLine, Declaration, PurchaseLine, ReviewState


def text(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        # 只去掉数据库固定标度的尾零，保留全部有效小数，不经浮点。
        rendered = format(value, "f")
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
    return str(value)


def unique_text(values):
    return "、".join(dict.fromkeys(value for value in values if value))


def line_number(value, index):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return index + 1


def line_bindings(content):
    """行级关联：子采购行 ID → 报关行 ID。"""
    return {
        link["purchase_line_id"]: link["customs_line_id"]
        for link in content["links"]
        if link["purchase_line_id"] and link["customs_line_id"]
    }


def purchase_line(order, row, basis=None, unit_names=None):
    declared = f"{text(row['declared_quantity'])} {unit_label(row['declared_unit'], unit_names)}".strip()
    note = "开票口径：子采购数量、单位与含税金额，审核通过后冻结为应开数量和金额。"
    if declared:
        note += f"报关数量 {declared}。"
    if row["amount_status"] == "source_missing":
        note += "来源金额缺失，开票后只能人工按差异结束。"
    return PurchaseLine(
        id=f"purchase-{row['id']}",
        name=text(row["declaration_name"] or row["item_name"]),
        model=text(row["specification"]),
        parent=text(order["parent_order_no"]),
        child=text(order["order_no"]),
        supplier=text(order["supplier_name"]),
        quantity=text(row["quantity"]),
        unit=unit_label(row["unit"], unit_names),
        price=text(row["unit_price"]),
        amount=text(row["amount"]),
        currency=text(basis["currency"] if basis and basis["allowed"] else order["currency"]),
        scope="order",
        note=note,
    )


def review_state(state, active_review, allowed, reason):
    reviewed_at = (
        active_review["approved_at"].replace(tzinfo=UTC, microsecond=0).isoformat() if active_review else None
    )
    return ReviewState(
        status=state,
        label=STATUS_LABELS[state],
        allowed=allowed,
        reason=reason,
        revision=active_review["revision"] if active_review else None,
        reviewedAt=reviewed_at,
        reviewedBy=active_review["approved_by"] if active_review else None,
        note=(active_review or {}).get("note") or "",
    )


def margin_fields(margin):
    return {
        "margin": f"{margin['margin']}%" if margin["margin"] is not None else "",
        "marginStatus": margin["status"],
        "marginNote": margin["note"],
        # 仅展示最多六位小数；幅度与异常已按未舍入单价判定。
        "declaredUnitPriceCny": text(margin["declared"].quantize(Decimal("0.000001")))
        if margin["declared"] is not None
        else "",
        "combinedPurchaseUnitPrice": text(margin["purchase"].quantize(Decimal("0.000001")))
        if margin["purchase"] is not None
        else "",
    }


def declaration(content, state, changed, active_review, allowed, reason):
    head = content["declaration"]
    orders = {order["id"]: order for order in content["orders"]}
    bound = line_bindings(content)
    by_customs = defaultdict(list)
    rows_by_customs = defaultdict(list)
    for row in content["purchase_lines"]:
        rows_by_customs[bound.get(row["id"])].append(row)
        line = purchase_line(
            orders[row["purchase_order_id"]],
            row,
            content.get("bases", {}).get(row["id"]),
            content.get("unit_names"),
        )
        by_customs[bound.get(row["id"])].append(line)
    margins = {
        row["id"]: declared_margin(
            row,
            rows_by_customs[row["id"]],
            orders,
            content.get("sales_orders", {}),
            content.get("unit_names"),
        )
        for row in content["customs_lines"]
    }
    unlinked = by_customs[None]
    reasons = auto_review_reasons(
        state,
        changed,
        len(unlinked),
        content["purchase_lines"],
        all(
            (content.get("bases", {}).get(row["id"]) or {}).get("allowed")
            or orders[row["purchase_order_id"]]["currency"]
            for row in content["purchase_lines"]
        ),
        list(margins.values()),
    )
    customs_lines = [
        CustomsLine(
            id=f"customs-{row['id']}",
            parent=text(row.get("parent_order_no")),
            originPlace=text(row["origin_place"]),
            lineNo=line_number(row["line_no"], index),
            name=text(row["declaration_name"]),
            model=text(row["specification"]),
            quantity=text(row["declared_quantity"]),
            unit=unit_label(row["declared_unit"], content.get("unit_names")),
            price=text(row["unit_price"]),
            amount=text(row["amount"]),
            currency=text(row["currency"]),
            purchaseCount=len(by_customs[row["id"]]),
            purchaseLines=group_purchase_lines([line.model_dump() for line in by_customs[row["id"]]]),
            **margin_fields(margins[row["id"]]),
        )
        for index, row in enumerate(content["customs_lines"])
    ]
    return Declaration(
        id=str(head["id"]),
        currencyEvidenceSummary=_currency_evidence(content, orders),
        currencyChecks=[
            {
                "purchaseOrderId": str(o["id"]),
                "orderNumber": o["order_no"] or "",
                "currency": o["currency"] or "",
                "allowed": not o["currency"] and o["parent_relation_status"] != "unknown",
                "reason": o["currency_issue"] or "币种取自母采购单，无需人工填写",
            }
            for o in content["orders"]
            if not o["currency"]
        ],
        contentSha256=head["content_sha256"] or "",
        account=head["ns_account"],
        recordNumber=text(head["record_no"]),
        declaration=text(head["declaration_no"]),
        pl=unique_text(
            [text(row["pl_no"]) for row in content["customs_lines"]]
            + [text(order["pl_no"]) for order in content["orders"]]
        ),
        company=unique_text(text(row["company_name"]) for row in content["customs_lines"]),
        salesOrders=unique_text(text(row["sales_order_no"]) for row in content["customs_lines"]),
        customsCount=len(customs_lines),
        purchaseCount=len(content["purchase_lines"]),
        customsLines=customs_lines,
        unlinkedLines=group_purchase_lines([line.model_dump() for line in unlinked]),
        marginAlert=margin_alert(margins.values()),
        autoReview=AutoReview(eligible=not reasons, reasons=reasons),
        warnings=[CHANGED_WARNING] if changed else [],
        review=review_state(state, active_review, allowed, reason),
    )


def line_digest(order, row):
    fields = {
        "order": order["ns_internal_id"],
        "line": row["source_line_key"],
        "quantity": text(row["quantity"]),
        "unit": text(row["unit"]),
        "amount": text(row["amount"]),
        "currency": text(order["currency"]),
    }
    encoded = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def review_lines(content):
    """审核冻结范围：有效关联子采购单的全部有效明细（开票口径）。"""
    orders = {order["id"]: order for order in content["orders"]}
    bound = line_bindings(content)
    rows = []
    for row in content["purchase_lines"]:
        order = orders[row["purchase_order_id"]]
        rows.append(
            {
                "purchase_order_id": order["id"],
                "purchase_line_id": row["id"],
                "customs_line_id": bound.get(row["id"]),
                "supplier_id": order["supplier_id"],
                "company_id": order["company_id"],
                "order_no": order["order_no"],
                "item_name": row["declaration_name"] or row["item_name"],
                "specification": row["specification"],
                "currency": order["currency"],
                "quantity": row["quantity"],
                "unit": row["unit"],
                "amount": row["amount"],
                "line_sha256": line_digest(order, row),
            }
        )
    return rows


def approved_lines(rows, ids):
    return tuple(
        ApprovedLine(
            review_line_id=line_id,
            purchase_basis_id=row.get("purchase_basis_id"),
            purchase_order_id=row["purchase_order_id"],
            purchase_line_id=row["purchase_line_id"],
            supplier_id=row["supplier_id"],
            company_id=row["company_id"],
            order_no=row["order_no"],
            currency=row["currency"],
            quantity=row["quantity"],
            unit=row["unit"],
            amount=row["amount"],
        )
        for row, line_id in zip(rows, ids)
    )


def _currency_evidence(content, orders):
    return list(
        dict.fromkeys(
            f"{orders[b['purchase_order_id']]['order_no']}：{b['currency']}，证据 {b['currency_evidence']['reference']}；{b['currency_evidence']['note']}"
            for b in content.get("bases", {}).values()
            if b["allowed"] and b["currency_source"] == "manual_verified"
        )
    )
