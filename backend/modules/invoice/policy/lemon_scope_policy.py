"""API 导入范围及结果说明；候选值来自默认范围和真实上游返回。"""


def lemon_import_defaults():
    return ["采购固定资产", "采购支出"]


def lemon_detail_ids(records, business_types):
    """只为本次选择范围读取商品明细；范围外旧票仍由保存用例处理失效。"""
    return {
        row["InvoiceId"]
        for row in records
        if isinstance(row.get("BusinessTypeText"), str) and row["BusinessTypeText"].strip() in business_types
    }


def lemon_business_type_options(result):
    result = result or {}
    return sorted(
        set(lemon_import_defaults())
        | set(result.get("availableBusinessTypes", []))
        | set(result.get("businessTypes", []))
    )


def describe_lemon_result(result):
    """同时修正历史已完成记录的展示，不改写历史统计或请求。"""
    value = dict(result)
    value.setdefault("completeDetails", 0)
    created, updated = value.get("created", 0), value.get("updated", 0)
    value["saved"] = bool(created or updated)
    if created or updated:
        value["message"] = f"已保存：新增 {created} 张，更新 {updated} 张。"
        if value["completeDetails"]:
            value["message"] += (
                f"明细完整 {value['completeDetails']} 张；符合条件的发票已按已审核子采购行生成建议，须人工确认。"
            )
        if value.get("pendingDetails", 0):
            value["message"] += f"明细待补齐或待核实 {value['pendingDetails']} 张，不能确认逐行匹配。"
    elif not value.get("fetched", 0):
        value["message"] = "所选日期范围内未查到进项发票，本次未新增或更新。"
    elif value.get("excluded", 0) == value["fetched"]:
        value["message"] = (
            f"读取 {value['fetched']} 张，全部不在所选业务类型内，本次未保存发票。请调整业务类型后重新拉取。"
        )
    else:
        value["message"] = (
            f"符合范围的 {value.get('unchanged', 0)} 张发票均已存在且未变化，本次未新增或更新。"
        )
    return value
