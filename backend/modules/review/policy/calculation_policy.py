"""查询投影版本与失效提示。金额规则变化时提升版本，启动后补算。"""

CALCULATION_VERSION = "review-v6"  # v6：比较单价前要求双方报关数量一致，旧快照启动后自动重算。
PENDING_REASON = "来源或审核已更新，后台计算中，请稍后刷新"
FAILED_REASON = "后台计算失败，系统将自动重试，请稍后刷新"


def calculation_key(tolerance):
    return f"{CALCULATION_VERSION}:cny={tolerance:.2f}"
