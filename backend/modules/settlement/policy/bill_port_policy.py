"""提单口岸文字的边界与跨行整理；只回拼原有字符，不补猜地名。"""

import re

MAX_PORT_LINES = 8
_PORT = re.compile(r"[A-Z][A-Z .,'()/-]{2,199}")
_FIELD_LABEL = re.compile(
    r"\b(?:PORT\s+OF|PLACE\s+OF|FINAL(?:\s+DESTINATION)?|VESSEL|VOYAGE|PRE[- ]CARRIAGE|"
    r"DELIVERY|RECEIPT|ROUTING|CONTAINER|SEAL|MARKS|NUMBER\s+AND|KIND\s+OF|PACKAGES|"
    r"DESCRIPTION|GROSS|NET\s+WEIGHT|MEASUREMENTS?|TOTAL|ON\s+BOARD|LADEN|SHIPPED|"
    r"FREIGHT|DATED|DATE\s+OF|ISSUE|SIGNED|SHIPPER|CONSIGNEE|NOTIFY|BOOKING|BILL\s+OF\s+LADING|B/L)\b"
)
_FIELD_HEADS = {
    "PORT",
    "PLACE",
    "FINAL",
    "VESSEL",
    "VOYAGE",
    "PRE-CARRIAGE",
    "DELIVERY",
    "RECEIPT",
    "ROUTING",
    "CONTAINER",
    "SEAL",
    "MARKS",
    "NUMBER",
    "KIND",
    "PACKAGES",
    "DESCRIPTION",
    "GROSS",
    "NET",
    "MEASUREMENT",
    "MEASUREMENTS",
    "TOTAL",
    "ON",
    "LADEN",
    "SHIPPED",
    "FREIGHT",
    "DATED",
    "DATE",
    "ISSUE",
    "SIGNED",
    "SHIPPER",
    "CONSIGNEE",
    "NOTIFY",
    "BOOKING",
    "B/L",
}
# 这些词本身不是完整口岸；遇到断行、空行或下一栏截断时不能把它们当作已识别。
_INCOMPLETE = {"LOS", "LAS", "SAN", "SANTA", "SANTO", "NEW", "UN", "UNITED", "PORT", "PLACE"}
# 仅修复原文全部字符已经存在的固定英文短语，不把缩写扩写成国家名称。
_PHRASES = {
    value.replace(" ", ""): value
    for value in (
        "UNITED STATES",
        "UNITED STATES OF AMERICA",
        "UNITED KINGDOM",
    )
}


def field_label(text, following=""):
    # PORT / KLANG 是地名续行；PORT / OF / LOADING 才是下一栏标题。
    if text.upper().strip() in {"PORT", "PLACE"}:
        return bool(re.match(r"OF\b", following.lstrip().upper()))
    return bool(_FIELD_LABEL.search(text.upper())) or field_head(text)


def field_head(text):
    """识别分行栏位标题的首词，避免把 NUMBER / AND KIND OF 等拆行标题拼入口岸。"""
    return text.upper().strip().rstrip(".:") in _FIELD_HEADS


def port_lines(lines):
    """连续同栏多行转口岸；超限、噪声、残缺或夹入其他栏位时整项留空。"""
    if not lines or len(lines) > MAX_PORT_LINES:
        return ""
    value = " ".join(line.strip() for line in lines).upper().strip(" .-/*")
    if not _PORT.fullmatch(value) or field_label(value) or value.endswith(","):
        return ""
    parts = [re.sub(r"\s+", " ", part).strip() for part in value.split(",")]
    if any(not part or part.replace(" ", "") in _INCOMPLETE for part in parts):
        return ""
    if any(len(part.replace(" ", "")) == 1 for part in parts[1:]):
        return ""
    for index, part in enumerate(parts):
        compact = part.replace(" ", "")
        if index and compact in _PHRASES:
            parts[index] = _PHRASES[compact]
        elif index and re.fullmatch(r"[A-Z](?: [A-Z]){1,2}", part):
            # 如逗号之间的 C / A 被窄单元格拆开，回拼为 CA，不增删字符。
            parts[index] = compact
    return ", ".join(parts)


def port_value(text):
    return port_lines(text.splitlines())
