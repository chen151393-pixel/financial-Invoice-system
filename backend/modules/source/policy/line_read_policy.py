"""同步明细的最小字段集：配置的展示/保存字段，以及现有逐行定位规则使用的原生引用。"""

PURCHASE_REFERENCES = {
    "custrecord_swc_subpo_main",
    "custrecord_swc_subpo_item_item",
    "custrecord_swc_subpo_item_ifreqid",
}
PURCHASE_VALUES = {
    "custrecord_swc_subpo_item_lineid",
    "custrecord_swc_subpo_item_name",
    "custrecord_swc_subpo_item_bgname",
    "custrecord_swc_subpo_item_qty",
    "custrecord_swc_subpo_item_unit",
    "custrecord_swc_subpo_item_bgqty",
    "custrecord_swc_subpo_item_bgunit",
    "custrecord_swc_subpo_item_ratewithrate",
    "custrecord_swc_subpo_item_amountwithtax",
    "custrecord_swc_subpo_item_mainpo_lineid",
    "custrecord_swc_subpo_item_solineid",
}
CUSTOMS_REFERENCES = {
    "custrecord_swc_relate_record",
    "custrecord_swc_packing_no",
    "custrecord_swc_company",
    "custrecord_swc_goods_place",
    "custrecord_swc_salesorder_number",
    "custrecord_swc_purachse_no",
    "custrecord_swc_currency",
    "custrecord_swc_itemcode",
}
CUSTOMS_VALUES = {
    "custrecord_swc_delare_name",
    "custrecord_swc_huge",
    "custrecord_swc_quantity",
    "custrecord_swc_unit",
    "custrecord_swc_delare_quantity",
    "custrecord_swc_delare_unit",
    "custrecord_swc_unitprice",
    "custrecord_swc_grossamountzj",
    "custrecord_swc_grossamount",
}


def line_projection(spec):
    """未知记录/字段继续使用原详情通道；已支持映射的批量查询失败必须明确报错。"""
    configured = set(spec.fields.values()) | set(spec.storage_fields.values())
    if spec.type == "customrecord_swc_subpo_item":
        # 商品等引用仅取 ID 定位；其 SuiteQL 显示名可能与 REST 不同，作为展示映射时仍走原通道。
        if configured & PURCHASE_REFERENCES:
            return None
        references, values = PURCHASE_REFERENCES, PURCHASE_VALUES
        required = references | {
            "custrecord_swc_subpo_item_mainpo_lineid",
            "custrecord_swc_subpo_item_solineid",
            "custrecord_swc_subpo_item_bgname",
        }
    elif spec.type == "customrecord_swc_delare_detail":
        references, values = CUSTOMS_REFERENCES, CUSTOMS_VALUES
        required = {
            "custrecord_swc_relate_record",
            "custrecord_swc_packing_no",
            "custrecord_swc_company",
            "custrecord_swc_goods_place",
            "custrecord_swc_delare_name",
            spec.pl,
            spec.company,
        }
    else:
        return None
    fields = required | {spec.parent} | configured
    if fields - (references | values):
        return None
    return {field: field in references for field in sorted(fields)} | {"isInactive": False}
