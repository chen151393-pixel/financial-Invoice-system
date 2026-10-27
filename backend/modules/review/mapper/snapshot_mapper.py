"""将已计算的展示结果转换成财务查询投影。"""


def snapshot_rows(content, group, changed, active, now):
    head = content["declaration"]
    tokens = [group.recordNumber, group.declaration, group.pl]
    for line in content["customs_lines"]:
        tokens.extend(str(line.get(key) or "") for key in ("pl_no", "item_name", "declaration_name"))
    for line in content["purchase_lines"]:
        tokens.extend(str(line.get(key) or "") for key in ("item_name", "declaration_name"))
    tokens.extend(order.get("order_no") or "" for order in content["orders"])
    row = dict(
        customs_declaration_id=head["id"],
        ns_account=head["ns_account"],
        declaration_date=head["declaration_date"],
        review_status=group.review.status,
        source_changed=changed,
        approved_at=active["approved_at"] if active else None,
        margin_alert=group.marginAlert,
        auto_eligible=group.autoReview.eligible,
        search_text="\n".join(tokens),
        payload=group.model_dump_json(),
        calculated_at=now,
        updated_at=now,
    )
    suppliers = {
        order["supplier_id"]: dict(
            declaration_id=head["id"],
            supplier_id=order["supplier_id"],
            ns_account=head["ns_account"],
            name=order.get("supplier_name") or f"供应商 {order['supplier_id']}",
        )
        for order in content["orders"]
        if order["supplier_id"]
    }
    return row, list(suppliers.values())
