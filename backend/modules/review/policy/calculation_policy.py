"""查询投影版本与失效提示。金额规则变化时提升版本，启动后补算。"""

# review-v18：后台计算同时刷新海关回执保存的比对结论与差异类型（规则变化后概况计数不再滞后）。
# 海关比对规则（customs_match_policy）变化时同样提升版本，启动后自动重新比对。
CALCULATION_VERSION = "review-v18"
PENDING_REASON = "来源或审核已更新，后台计算中，请稍后刷新"
FAILED_REASON = "后台计算失败，系统将自动重试，请稍后刷新"


def calculation_key(tolerance):
    return f"{CALCULATION_VERSION}:cny={tolerance:.2f}"
