"""人工更新来源只接受完整、有效且仍同客户同币种的直接收汇组。"""

from backend.core.names import normalize_name


def update_reason(rows):
    if not rows or any(
        row.get("route") != "direct"
        or not row.get("consignee")
        or not row.get("currency")
        or row.get("currency_issue")
        or row.get("amount") is None
        for row in rows
    ):
        return "存在缺失或无效的直接收汇依据，请先核对海关回执和 NS 关联"
    if len({normalize_name(row["consignee"]) for row in rows}) != 1:
        return "组内当前境外收货人不一致，不能更新为跨客户资料组，请先核对来源"
    if len({row["currency"] for row in rows}) != 1:
        return "组内当前币种不一致，不能更新为跨币种资料组，请先核对来源"
    return ""
