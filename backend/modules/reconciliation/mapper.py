"""只按NS显式父行引用组成展示树，不按品名、PL或相邻行猜配。"""

import re
from datetime import UTC, datetime

from backend.modules.business.public import relation_digest as digest

from .vo import CustomsLine, Declaration, PurchaseLine, ReviewState


def unique_text(values):
    return "、".join(dict.fromkeys(value for value in values if value and value not in {"未填写", "待确认"}))


def purchase(row):
    cells = row["cells"]
    return PurchaseLine(
        id=row["id"],
        name=cells[9],
        model=cells[10],
        parent=cells[4],
        child=cells[5],
        supplier=cells[7],
        quantity=cells[11],
        unit=cells[12],
        price=cells[13],
        amount=cells[14],
        currency=row.get("currency", ""),
        note=row["note"],
    )


def declaration(raw, version):
    customs = [row for row in raw["rows"] if row["side"] == "customs"]
    purchases = [row for row in raw["rows"] if row["side"] == "purchase"]
    rows = []
    for index, row in enumerate(customs):
        cells = row["cells"]
        linked = [
            purchase(item) for item in purchases if version == 3 and item.get("customsRowId") == row["id"]
        ]
        rows.append(
            CustomsLine(
                id=row["id"],
                lineNo=index + 1,
                name=cells[9],
                model=cells[10],
                quantity=cells[11],
                unit=cells[12],
                price=cells[15] if len(cells) == 17 else cells[13],
                amount=cells[14],
                currency=cells[16] if len(cells) == 17 else "",
                purchaseCount=len(linked),
                purchaseLines=linked,
            )
        )
    return Declaration(
        id=raw.get("declarationId") or digest(raw["id"]),
        recordNumber=raw.get("recordNumber") or re.sub(r"^报关单\s+", "", raw["title"]),
        declaration=unique_text(row["cells"][0] for row in customs),
        pl=raw.get("plNumbers") or unique_text(row["cells"][2] for row in raw["rows"]),
        company=raw.get("company") or unique_text(row["cells"][8] for row in customs),
        customsCount=len(customs),
        purchaseCount=len(purchases),
        customsLines=rows,
        unlinkedLines=[purchase(row) for row in purchases if version != 3 or not row.get("customsRowId")],
        warnings=raw["warnings"],
        review=ReviewState(status="pending", label="待审核", allowed=False, reason=""),
    )


def review_state(head, source_digest, reason):
    approved = head["digest"] == source_digest
    status = "approved" if approved else "blocked" if reason else "pending"
    return ReviewState(
        status=status,
        label={"pending": "待审核", "blocked": "待核实", "approved": "审核通过"}[status],
        allowed=not approved and not reason,
        reason=reason if not approved else "",
        reviewedAt=datetime.fromtimestamp(head["reviewed_at"], UTC).isoformat() if approved else None,
        reviewedBy=head["reviewed_by"] if approved else None,
        note=(head["note"] or "") if approved else "",
    )
