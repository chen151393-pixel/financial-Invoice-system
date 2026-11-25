"""查询投影版本与失效提示。金额规则变化时提升版本，启动后补算。"""

# review-v19：零金额采购行按未税金额零参与计算，保留其采购数量；重建旧的不可计算快照。
# 海关比对规则（customs_match_policy）变化时同样提升版本，启动后自动重新比对。
CALCULATION_VERSION = "review-v19"
PENDING_REASON = "来源或审核已更新，后台计算中，请稍后刷新"
FAILED_REASON = "后台计算失败，系统将自动重试，请稍后刷新"


def calculation_key(tolerance):
    return f"{CALCULATION_VERSION}:cny={tolerance:.2f}"
