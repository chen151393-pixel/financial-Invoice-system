"""仅用于子采购合同文件名的供应商简称，不改变来源名称或供应商匹配。"""

import re

from .supplier_group_policy import SUFFIXES

INDUSTRY_SUFFIXES = (
    "包装材料",
    "机械设备",
    "印刷设备",
    "数码科技",
    "智能科技",
    "环保科技",
    "电子科技",
    "纸制品",
    "纸业",
    "工贸",
    "包装",
    "电子",
    "机械",
    "设备",
    "贸易",
    "印刷",
    "科技",
    "实业",
)


def supplier_filename_name(value):
    name = (value or "").strip()
    short = next((name.removesuffix(suffix) for suffix in SUFFIXES if name.endswith(suffix)), name)
    # 保留地区与商号，只去开头城市名称后的“市”，不推测省份、行政区或品牌。
    short = re.sub(r"^([\u4e00-\u9fff]{2,4})市", r"\1", short, count=1)
    for suffix in INDUSTRY_SUFFIXES:
        if short.endswith(suffix) and len(short.removesuffix(suffix)) >= 4:
            short = short.removesuffix(suffix)
            break
    # 过短或只有企业后缀的异常名称保留原文，不生成空名称。
    return short if len(short) >= 2 else name
