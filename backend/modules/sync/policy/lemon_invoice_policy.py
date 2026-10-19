"""持久同步记录的请求范围；兼容未携带多选条件的历史请求。"""


def run_business_types(row):
    # 旧请求只导入固定资产，不能把新默认值套到旧请求的幂等判断中。
    return (row.get("result") or {}).get("businessTypes", ["采购固定资产"])
