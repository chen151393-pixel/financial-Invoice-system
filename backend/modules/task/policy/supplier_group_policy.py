"""供应商名称与外部群候选：只推荐，不凭名称自动绑定。"""

from backend.core.names import normalize_name

SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司")


def match_group(supplier_name, group, keyword=""):
    """返回排序优先级和可读依据；简称只去企业后缀，不猜测地域或品牌。"""
    full = normalize_name(supplier_name)
    name = normalize_name(group["groupName"])
    if keyword:
        term = normalize_name(keyword)
        fields = (group[key] for key in ("groupName", "employee", "userid", "chatId"))
        if term and any(term in normalize_name(value) for value in fields):
            return 3, "关键词匹配，请核对供应商与群主"
        return None
    if not full:
        return None
    if full == name:
        return 0, "群名与供应商名称一致"
    if len(full) >= 4 and full in name:
        return 1, "群名包含供应商全称"
    short = next((full.removesuffix(suffix) for suffix in SUFFIXES if full.endswith(suffix)), full)
    if short != full and len(short) >= 4 and short in name:
        return 2, "群名包含去除企业后缀后的名称，请核对"
    return None
