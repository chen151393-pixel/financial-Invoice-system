"""来源与业务门面返回的事实转为待办展示；不执行任何审核。"""

from datetime import UTC

from ..vo.workbench_vo import Todo


def iso(value):
    return value.replace(tzinfo=UTC).isoformat()


def review_todo(row):
    return Todo(
        key=f"review:{row['id']}",
        kind="review",
        targetId=str(row["id"]),
        title=row["record_no"] or row["declaration_no"] or f"报关记录 {row['id']}",
        subtitle=" / ".join(sorted(row["pls"])),
        party=" / ".join(sorted(row["suppliers"])) or row["company"] or "关联资料待补齐",
        account=row["ns_account"],
        amount=None,
        currency="",
        amountLabel="按子采购行核对",
        statusLabel="待财务核对",
        reason=row["reason"],
        createdAt=iso(row["created_at"]),
        priority=2,
    )


def task_todo(row, declarations):
    declaration = declarations.get(row["customs_declaration_id"], {})
    amount = row["outstanding"]
    return Todo(
        key=f"task:{row['id']}",
        kind="task",
        targetId=str(row["id"]),
        title=row["record_no"] or f"开票任务 {row['id']}",
        subtitle=" / ".join(row["orders"] + sorted(declaration.get("pls", []))),
        party=row["supplier"],
        account=row["ns_account"],
        amount=format(amount, "f") if amount is not None else None,
        currency=row["currency"] or "",
        amountLabel="待收含税金额",
        statusLabel=row["status_label"],
        reason=row["reason"],
        createdAt=iso(row["created_at"]),
        priority=3,
        attention=row["status"] in ("documents_pending", "notify_pending", "documents_incomplete"),
    )


def matching_todo(key, rows, invoice, contexts):
    invoice_id, account = key
    reverify = any(row["status"] == "confirmed" for row in rows)
    orders = sorted({contexts.get(row["purchase_line_id"], {}).get("order_no") or "" for row in rows})
    return Todo(
        key=f"matching:{invoice_id}:{account}",
        kind="matching",
        targetId=str(invoice_id),
        title=invoice.get("invoice_no") or f"发票 {invoice_id}",
        subtitle=" / ".join(filter(None, orders)),
        party=invoice.get("seller_name") or "供应商待确认",
        account=account,
        amount=None,
        currency=invoice.get("currency") or "",
        amountLabel="进入比对查看分配",
        statusLabel="待复核" if reverify else "待比对审核",
        reason="已确认分配的有效性变化，请核实当前发票和采购依据"
        if reverify
        else f"{len(rows)} 条建议待人工审核，尚未计为收票",
        createdAt=iso(min(row["created_at"] for row in rows)),
        priority=0 if reverify else 1,
        attention=reverify,
    )
