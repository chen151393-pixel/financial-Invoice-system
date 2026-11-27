"""回款路径判定（纯函数）。

业务规则（2026-11-17 确认）：按报关单“贸易国（地区）”分流——贸易国为中国香港走香港中转结汇，
贸易国为真实客户国家走直接收汇。海关回执导入文件目前不含贸易国，未取得贸易国时按境外收货人是否为
集团香港公司判定（名单可在配置 SETTLEMENT_HK_CONSIGNEES 中维护）。
"""

from backend.core.names import normalize_name

from .consignee_policy import consignee_key, consignee_names

HK_TRANSIT = "hk_transit"
DIRECT = "direct"
ROUTE_LABELS = {HK_TRANSIT: "香港中转", DIRECT: "直接收汇"}
HK_COUNTRY_NAMES = {"中国香港", "香港", "hongkong", "hkg", "hk"}

# 已知的集团香港公司（境外收货人）；配置项为空时使用。
DEFAULT_HK_CONSIGNEES = (
    "HONGKONG VISION DIGITAL PRINTING CO., LIMITED",
    "Hongkong Yesop Connect Supply Chain Management co. Limited",
    "HONGKONG C-B CONNECT LIMITED",
)


def hk_consignee_keys(names):
    return set(consignee_names(names or DEFAULT_HK_CONSIGNEES))


def route_of(trade_country, consignee, hk_keys):
    """返回 (路径, 依据说明)。"""
    country = normalize_name(trade_country)
    if country:
        if country in HK_COUNTRY_NAMES:
            return HK_TRANSIT, "贸易国为中国香港"
        return DIRECT, f"贸易国为{trade_country}"
    if consignee_key(consignee) in hk_keys:
        return HK_TRANSIT, "境外收货人为集团香港公司"
    return DIRECT, "境外收货人非集团香港公司"
