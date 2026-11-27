"""结汇客户名称匹配：仅消除格式差异，保留原始名称供展示与归档。"""

import unicodedata


def consignee_key(value):
    """全半角统一，去除符号、空白，统一大写；保留文字和数字后精确匹配。

    旧银行流水中保存的 customer_key 也走此规则，无须改写历史记录。
    """
    text = unicodedata.normalize("NFKC", str(value or "")).upper()
    return "".join(char for char in text if char.isalnum())


def consignee_names(names):
    """匹配键 → 配置原文；重复配置同一客户时，以第一项的展示格式为准。"""
    result = {}
    for name in names:
        key = consignee_key(name)
        if key:
            result.setdefault(key, name)
    return result


class ConsigneeDisplay:
    """单次查询使用的名称快照；香港配置覆盖已登记名称，不共享可变缓存。"""

    def __init__(self, names):
        self.names = names

    def display_name(self, consignee):
        return self.names.get(consignee_key(consignee), consignee)

    def display_consignee(self, row):
        return {**row, "consignee": self.display_name(row["consignee"])}
