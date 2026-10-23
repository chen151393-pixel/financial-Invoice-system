"""资料齐全规则（2026-10-23 业务确认），纯函数。

完结所需资料：每张子采购单的子采购合同与回签合同，以及所属报关单的报关单、销售合同、发票。
报关资料下载失败或未完成不影响通知供应商，只影响完结。
"""

DECLARATION_DOCUMENTS = {"customs_declaration": "报关单", "sales_contract": "销售合同", "invoice": "发票"}


def missing_documents(order_ids, archived_contracts, declaration_rows, signed_orders):
    """返回尚未到齐的资料名称列表；为空表示资料齐全。

    archived_contracts / signed_orders：已归档子采购合同、已上传回签合同的子采购单 ID 集合；
    declaration_rows：{资料类型: 记录}，记录 status 为 archived 才算到齐。
    """
    orders = set(order_ids)
    missing = []
    if not orders <= set(archived_contracts):
        missing.append("子采购合同")
    for doc_type, label in DECLARATION_DOCUMENTS.items():
        if (declaration_rows.get(doc_type) or {}).get("status") != "archived":
            missing.append(label)
    if not orders <= set(signed_orders):
        missing.append("回签合同")
    return missing
