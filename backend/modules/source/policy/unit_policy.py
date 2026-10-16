"""单位编号的展示名称；不换算数量，也不修改来源或冻结依据。"""

import re


def unit_label(value, names):
    original = "" if value is None else str(value)
    code = original.strip()
    # 只识别完整数字编号，文本单位、组合单位、未知编号均保留来源值。
    if re.fullmatch(r"[0-9]{1,10}", code):
        return (names or {}).get(str(int(code)), original)
    return original
