"""审核历史承接后的有效版本；原绑定列保留作为历史证据。"""


def effective_basis(row):
    return next(
        (
            h["purchaseBasisId"]
            for h in reversed(row["verification_history"] or [])
            if h.get("purchaseBasisId")
        ),
        row["purchase_basis_id"],
    )


def effective_invoice(row):
    return next(
        (
            h["invoiceVersionId"]
            for h in reversed(row["verification_history"] or [])
            if h.get("invoiceVersionId")
        ),
        row["invoice_version_id"],
    )
