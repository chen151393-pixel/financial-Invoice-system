"""从同一份报关来源快照补齐展示字段，不借用关联子采购单的字段。"""

from ..policy.local_relation_policy import source_records


def customs_display_lines(head, lines):
    _, records = source_records(
        head.get("raw_payload"),
        "customrecord_swc_declare_record",
        head["ns_internal_id"],
        "customrecord_swc_delare_detail",
    )
    result = []
    for line in lines:
        record = records.get(line["source_line_key"], {})
        parent = record.get("custrecord_swc_purachse_no")
        # 引用只有内部 ID 时不能把 ID 当作采购订单编号。
        if isinstance(parent, dict):
            parent = parent.get("refName")
        result.append({**line, "parent_order_no": str(parent) if parent else ""})
    return result
