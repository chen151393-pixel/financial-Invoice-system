"""查询投影版本与失效提示。金额规则变化时提升版本，启动后补算。"""

CALCULATION_VERSION = "review-v3"  # v3：保留 v2 单价幅度规则，补齐快照的关联子采购单号搜索字段。
PENDING_REASON = "来源或审核已更新，后台计算中，请稍后刷新"
FAILED_REASON = "后台计算失败，系统将自动重试，请稍后刷新"


def calculation_key(tolerance):
    return f"{CALCULATION_VERSION}:cny={tolerance:.2f}"
