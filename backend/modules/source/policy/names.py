"""名称规范化（数据库设计第 5.2 节）：供应商、公司、品名比对前统一处理。"""

import re
import unicodedata

# NFKC 已把全角圆括号转为半角；其余中文括号统一为半角方括号。
_BRACKETS = str.maketrans({"【": "[", "】": "]", "〔": "[", "〕": "]", "［": "[", "］": "]"})


def normalize_name(value):
    """全角转半角、去空白、括号统一、英文小写；不做模糊相似度计算。"""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"\s+", "", text).translate(_BRACKETS)
    return text.lower()
