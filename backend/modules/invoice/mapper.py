"""已校验文件的数据库对象转换，不访问数据库。"""

from .parser import digest


def storage_values(document, tenant, owner, filename, file_hash, now):
    head = {
        **document["head"],
        "tenant_id": tenant,
        "external_system": "excel",
        "external_account": "lemon-excel",
        "source_version": 1,
        "detail_sync_status": "complete",
        "is_active": True,
        "validation_status": "review",
        "validation_errors": [
            {"code": "BUYER_CURRENCY_UNVERIFIED", "message": "文件未提供购买方税号和币种，需核实后再参与匹配"}
        ],
        "created_at": now,
        "updated_at": now,
        "synced_at": now,
        "last_complete_sync_at": now,
        "source_data": {
            "schema_version": 1,
            "parser_version": "lemon_excel_v1",
            "file_name": filename,
            "file_sha256": file_hash,
            "import_batch_id": digest({"tenant": tenant, "file": file_hash}),
            "imported_by": owner,
            "imported_at": now.isoformat() + "Z",
            "header": {"sheet": "发票信息", **document["rawHead"]},
            "lines": [{"sheet": "货物信息", **row} for row in document["rawLines"]],
            "derived_fields": ["invoice_lines.amount_including_tax"],
        },
    }
    lines = [{**line, "tenant_id": tenant, "synced_at": now, "is_active": True} for line in document["lines"]]
    return head, lines


def image_storage_values(snapshot, tenant, owner, now):
    """将已校验的用户发票图片摘录转换为现有发票两表。"""
    head = {
        "tenant_id": tenant,
        "external_system": "manual",
        "external_account": "user-image",
        "external_record_id": snapshot["invoice_no"],
        "import_key": snapshot["import_key"],
        "content_hash": snapshot["content_hash"],
        "source_version": 1,
        "invoice_direction": "input",
        "invoice_type_name": snapshot["invoice_type_name"],
        "invoice_no": snapshot["invoice_no"],
        "invoice_date": snapshot["invoice_date"],
        "invoice_status": "unknown",
        "seller_name": snapshot["seller_name"],
        "seller_tax_no": snapshot["seller_tax_no"],
        "seller_bank_account": snapshot["seller_bank_account"],
        "buyer_name": snapshot["buyer_name"],
        "buyer_tax_no": snapshot["buyer_tax_no"],
        "currency_code": "CNY",
        "business_type_name": None,
        "tax_rate_summary": snapshot["tax_rate_raw"],
        "amount_excluding_tax": snapshot["amount_excluding_tax"],
        "tax_amount": snapshot["tax_amount"],
        "amount_including_tax": snapshot["amount_including_tax"],
        "remark": snapshot["remark"],
        "detail_sync_status": "complete",
        "last_complete_sync_at": now,
        "synced_at": now,
        "is_active": True,
        "validation_status": "review",
        "validation_errors": snapshot["validation_errors"],
        "created_at": now,
        "updated_at": now,
        "source_data": {
            "schema_version": 1,
            "source_kind": "user_attached_image",
            "file_name": snapshot["source_name"],
            "file_sha256": snapshot["source_hash"],
            "imported_by": owner,
            "imported_at": now.isoformat() + "Z",
            "header": snapshot["raw_header"],
            "lines": snapshot["raw_lines"],
            "derived_fields": ["invoice_lines.amount_including_tax"],
        },
    }
    lines = [
        {
            "tenant_id": tenant,
            "source_line_key": line["source_line_key"],
            "line_no": str(index),
            "item_name": line["item_name"],
            "unit_name": line["unit_name"],
            "quantity": line["quantity"],
            "unit_price": line["unit_price"],
            "amount_excluding_tax": line["amount_excluding_tax"],
            "tax_rate_raw": snapshot["tax_rate_raw"],
            "tax_rate": snapshot["tax_rate"],
            "tax_treatment": "rate",
            "tax_amount": line["tax_amount"],
            "amount_including_tax": line["amount_including_tax"],
            "synced_at": now,
            "is_active": True,
        }
        for index, line in enumerate(snapshot["lines"], 1)
    ]
    return head, lines
