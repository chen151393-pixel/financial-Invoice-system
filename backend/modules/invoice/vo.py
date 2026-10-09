"""导入预览和提交结果；金额仅返回十进制文本。"""


def decimal_text(value):
    return format(value, "f") if value is not None else None


def invoice_row(row):
    return {
        "id": str(row["id"]),
        "number": row["invoice_no"],
        "date": row["invoice_date"].isoformat() if row["invoice_date"] else None,
        "seller": row["seller_name"],
        "sellerTaxNo": row["seller_tax_no"],
        "type": row["invoice_type_name"],
        "businessType": row["business_type_name"],
        "status": row["invoice_status_raw"]
        or {"normal": "正常", "red_offset": "已红冲", "void": "作废"}.get(row["invoice_status"], "未知"),
        "validation": {"pending": "待校验", "review": "待核实", "passed": "已通过", "failed": "未通过"}.get(
            row["validation_status"], "未知"
        ),
        "currency": row["currency_code"],
        "net": decimal_text(row["amount_excluding_tax"]),
        "tax": decimal_text(row["tax_amount"]),
        "gross": decimal_text(row["amount_including_tax"]),
        "lineCount": row["line_count"],
        "importedAt": row["synced_at"].isoformat() + "Z" if row["synced_at"] else None,
        "source": {
            "excel": "Excel导入",
            "manual": "图片录入",
        }.get(row["external_system"], row["external_system"]),
    }


def invoice_detail_view(head, lines):
    result = invoice_row({**head, "line_count": len(lines)})
    result.update(
        sourceComplete=head.get("detail_sync_status") == "complete",
        sourceStatus=head["invoice_status"],
        buyer=head["buyer_name"],
        buyerTaxNo=head["buyer_tax_no"],
        remark=head["remark"],
        project=head["project_name"],
        department=head["department_name"],
        employee=head["employee_name"],
        voucher=head["voucher_reference"],
        invoiceCode=head["invoice_code"],
        validationMessages=[
            item["message"]
            for item in (head["validation_errors"] or [])
            if isinstance(item, dict) and isinstance(item.get("message"), str)
        ],
        lines=[
            {
                "id": str(line["id"]),
                "number": line["line_no"],
                "item": line["item_name"],
                "specification": line["specification"],
                "unit": line["unit_name"],
                "quantity": decimal_text(line["quantity"]),
                "unitPrice": decimal_text(line["unit_price"]),
                "net": decimal_text(line["amount_excluding_tax"]),
                "taxRate": line["tax_rate_raw"],
                "tax": decimal_text(line["tax_amount"]),
                "gross": decimal_text(line["amount_including_tax"]),
            }
            for line in lines
        ],
    )
    return result


def result(documents, actions):
    return {
        "invoiceCount": len(documents),
        "lineCount": sum(len(doc["lines"]) for doc in documents),
        "created": actions.count("new"),
        "unchanged": actions.count("unchanged"),
        "conflicts": actions.count("conflict"),
        "amount": format(sum(doc["head"]["amount_including_tax"] for doc in documents), "f"),
        "rows": [
            {
                "number": doc["head"]["invoice_no"],
                "date": doc["head"]["invoice_date"].isoformat(),
                "seller": doc["head"]["seller_name"],
                "businessType": doc["head"]["business_type_name"],
                "status": doc["head"]["invoice_status_raw"] or "未知",
                "amount": format(doc["head"]["amount_including_tax"], "f"),
                "lineCount": len(doc["lines"]),
                "action": action,
            }
            for doc, action in zip(documents, actions, strict=True)
        ],
        "warnings": [
            "购方税号与币种未核实，所有新发票以待核实状态保存，不自动匹配或写回NS。",
            "仅导入采购固定资产发票；含税金额为筛选后的带符号合计，不代表可抵扣或可匹配金额。",
        ],
    }
