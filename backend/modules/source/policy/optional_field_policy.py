"""已知非关键展示字段缺失的边界；缺失代表未知，不能推断为空或沿用旧值。"""

OPTIONAL_CUSTOMS_FIELDS = {
    "specification": "custrecord_swc_huge",
    # NS 自 2026-08-17 起才填写申报单价，此前的报关行为空；按 NULL 保存，核对时由 source 规则试算。
    "declared_unit_price": "custrecord_swc_grossamountzj",
}

# 子采购明细的税码可能未填写；缺失时税率为 NULL，发票比对的税额项显示“未校验”。
OPTIONAL_PURCHASE_FIELDS = {"tax_rate": "custrecord_swc_subpo_item_tax"}


def allows_missing(kind, spec, key):
    # 只放行已知字段；拼错映射、其他记录类型及金额等字段仍失败。
    if kind == "purchase_line":
        return (
            spec.type == "customrecord_swc_subpo_item"
            and key in OPTIONAL_PURCHASE_FIELDS
            and spec.storage_fields.get(key) == OPTIONAL_PURCHASE_FIELDS[key]
        )
    return (
        kind == "customs_line"
        and spec.type == "customrecord_swc_delare_detail"
        and key in OPTIONAL_CUSTOMS_FIELDS
        and spec.storage_fields.get(key) == OPTIONAL_CUSTOMS_FIELDS[key]
    )


def warnings(bundle, config):
    spec = config.customs_line
    if not allows_missing("customs_line", spec, "specification"):
        return []
    field = spec.storage_fields["specification"]
    result = []
    for identity, head, lines in bundle["customs"]:
        count = sum(field not in record for _, record in lines)
        if count:
            number = head.get("name") or identity
            result.append(
                f"报关单 {number} 有 {count} 条明细未返回规格型号（{field}），已按未知值保存；"
                "请核实 NS 字段填写或可见性。未沿用旧型号或推断型号。"
            )
    return result
