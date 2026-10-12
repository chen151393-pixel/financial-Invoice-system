"""source 报关单内容 → 财务核对展示；审核冻结行。纯转换，不查询数据库。"""

import hashlib
import json
from collections import defaultdict
from datetime import UTC
from decimal import Decimal

from ..policy.review_policy import CHANGED_WARNING, STATUS_LABELS
from ..public import ApprovedLine
from ..vo.review_vo import CustomsLine, Declaration, PurchaseLine, ReviewState


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


def purchase_line(order, row):
    declared = f"{text(row['declared_quantity'])} {text(row['declared_unit'])}".strip()
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
        unit=text(row["unit"]),
        price=text(row["unit_price"]),
        amount=text(row["amount"]),
        currency=text(order["currency"]),
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


def declaration(content, state, changed, active_review, allowed, reason):
    head = content["declaration"]
    orders = {order["id"]: order for order in content["orders"]}
    bound = line_bindings(content)
    by_customs = defaultdict(list)
    for row in content["purchase_lines"]:
        by_customs[bound.get(row["id"])].append(purchase_line(orders[row["purchase_order_id"]], row))
    customs_lines = [
        CustomsLine(
            id=f"customs-{row['id']}",
            lineNo=line_number(row["line_no"], index),
            name=text(row["declaration_name"]),
            model=text(row["specification"]),
            quantity=text(row["declared_quantity"]),
            unit=text(row["declared_unit"]),
            price=text(row["unit_price"]),
            amount=text(row["amount"]),
            currency=text(row["currency"]),
            purchaseCount=len(by_customs[row["id"]]),
            purchaseLines=by_customs[row["id"]],
        )
        for index, row in enumerate(content["customs_lines"])
    ]
    return Declaration(
        id=str(head["id"]),
        contentSha256=head["content_sha256"] or "",
        account=head["ns_account"],
        recordNumber=text(head["record_no"]),
        declaration=text(head["declaration_no"]),
        pl=unique_text(
            [text(row["pl_no"]) for row in content["customs_lines"]]
            + [text(order["pl_no"]) for order in content["orders"]]
        ),
        company=unique_text(text(row["company_name"]) for row in content["customs_lines"]),
        customsCount=len(customs_lines),
        purchaseCount=len(content["purchase_lines"]),
        customsLines=customs_lines,
        unlinkedLines=by_customs[None],
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
