"""同一账本事务内核实双审核，放行一次；不直接写入 task。"""

from datetime import UTC, datetime

from backend.modules.source.public import declarations_by_number, digest, snapshot

from ..dao import (
    customs_approval_dao,
    customs_receipt_dao,
    purchase_basis_dao,
    review_line_dao,
    review_record_dao,
)
from ..mapper.declaration_mapper import approved_lines
from ..public import InvoiceReady


def release_if_ready(connection, declaration_id, events):
    content = snapshot(connection, declaration_id)
    if content is None:
        return
    head = content["declaration"]
    review = review_record_dao.active(connection, declaration_id, lock=True)
    current_digest = digest(content)
    if (
        not review
        or review["content_sha256"] != current_digest
        or head["content_sha256"] != current_digest
        or purchase_basis_dao.required_declarations(connection, [review["id"]])
        or review["customs_approval_id"] is not None
    ):
        return
    candidates = declarations_by_number(connection, [head["declaration_no"]]).get(head["declaration_no"], [])
    if len(candidates) != 1 or candidates[0]["id"] != declaration_id:
        return
    receipt = customs_receipt_dao.heads_by_numbers(connection, [head["declaration_no"]]).get(
        head["declaration_no"]
    )
    approval = (
        customs_approval_dao.current(connection, receipt, declaration_id, current_digest) if receipt else None
    )
    if not approval:
        return
    now = datetime.now(UTC).replace(tzinfo=None)
    if not review_record_dao.release(connection, review["id"], approval["id"], now):
        return
    rows = review_line_dao.by_review(connection, review["id"])
    previous = next(
        (
            row
            for row in review_record_dao.history(connection, declaration_id)
            if row["revision"] < review["revision"]
        ),
        None,
    )
    events.publish(
        connection,
        InvoiceReady(
            review_id=review["id"],
            superseded_review_id=previous["id"] if previous else None,
            ns_account=head["ns_account"],
            customs_declaration_id=declaration_id,
            record_no=review["record_no"],
            revision=review["revision"],
            approved_by=review["approved_by"],
            lines=approved_lines(rows, [row["id"] for row in rows]),
        ),
    )


def on_finance_approved(connection, event, *, events):
    release_if_ready(connection, event.customs_declaration_id, events)
