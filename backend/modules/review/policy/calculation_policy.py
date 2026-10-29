"""查询投影版本与失效提示。金额规则变化时提升版本，启动后补算。"""

CALCULATION_VERSION = "review-v5"  # v5：展示报关数量与原采购含税单价，幅度比较使用折算报关单价。
PENDING_REASON = "来源或审核已更新，后台计算中，请稍后刷新"
FAILED_REASON = "后台计算失败，系统将自动重试，请稍后刷新"


def calculation_key(tolerance):
    return f"{CALCULATION_VERSION}:cny={tolerance:.2f}"
