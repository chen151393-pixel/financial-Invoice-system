"""已知非关键展示字段缺失的边界；缺失代表未知，不能推断为空或沿用旧值。"""


def allows_missing(kind, spec, key):
    # 只放行已知报关明细的规格型号；拼错映射、其他记录类型及金额等字段仍失败。
    return (
        kind == "customs_line"
        and spec.type == "customrecord_swc_delare_detail"
        and key == "specification"
        and spec.storage_fields.get(key) == "custrecord_swc_huge"
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
