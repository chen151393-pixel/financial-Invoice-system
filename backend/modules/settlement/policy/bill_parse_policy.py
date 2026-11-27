"""提单文字解析（纯函数）：从 PDF 文字中尽力识别提单号、装运口岸、目的口岸与装船日期。

各船公司版式不同，识别不到的字段留空，由人工在页面补填；本模块不做任何默认值或猜测港口。
"""

import re
from datetime import date, datetime

from .bill_port_policy import MAX_PORT_LINES, field_label, port_lines

_MONTHS = {
    name: index
    for index, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1
    )
}
_DATE_PATTERNS = (
    # 2026-06-15 / 2026/06/15
    (r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    # JUN 15 2026 / JUN.15,2026
    (r"([A-Z]{3})[A-Z]*[ .,-]+(\d{1,2})[ .,-]+(\d{4})", lambda m: (int(m[3]), _MONTHS.get(m[1]), int(m[2]))),
    # 15 JUN 2026 / 15-JUN-2026
    (r"(\d{1,2})[ .,-]+([A-Z]{3})[A-Z]*[ .,-]+(\d{4})", lambda m: (int(m[3]), _MONTHS.get(m[2]), int(m[1]))),
)
_BL_LABEL = re.compile(
    r"(?:B\s*/?\s*L|BILL\s+OF\s+LADING|WAYBILL)\s*(?:NO|NUMBER)\s*\.?\s*[:：]?\s*([A-Z0-9]{8,20})\b"
)
# 常见提单号形态：四位船公司代码 + 数字（如 EGLV142503975412、OOLU2156789012）
_BL_SHAPE = re.compile(r"\b[A-Z]{4}\d{7,15}\b")
_ON_BOARD = re.compile(
    r"(?:ON\s+BOARD\s+DATE|LADEN\s+ON\s+BOARD(?:\s+THE\s+VESSEL)?|SHIPPED\s+ON\s+BOARD(?:\s+DATE)?)"
    r"[^0-9A-Z]{0,12}(?:DATE)?[^0-9A-Z]{0,6}([0-9A-Z ./,-]{6,20})"
)


def parse_date(text):
    """识别一个日期；无法识别返回 None。"""
    upper = (text or "").upper()
    for pattern, build in _DATE_PATTERNS:
        match = re.search(pattern, upper)
        if not match:
            continue
        year, month, day = build(match)
        try:
            return date(year, month, day) if month else None
        except ValueError:
            continue
    return None


def _port(upper, label):
    """提取标签后的连续多行，以空行或下一栏位结束；并排标签时不猜列归属。

    不能在遇到噪声或行数上限时退回第一行，否则 LOS 等碎片会冒充完整口岸。
    """
    match = re.search(label, upper)
    if not match:
        return ""
    start = upper.rfind("\n", 0, match.start()) + 1
    end = upper.find("\n", match.end())
    end = len(upper) if end == -1 else end
    before, after = upper[start : match.start()], upper[match.end() : end]
    if before.strip(" .:0123456789") or field_label(after):
        return ""
    first = after.lstrip(" :：").strip()
    if re.search(r"\S(?:\t| {3,})\S", first):
        return ""
    values = [first] if first else []
    tail = upper[end + 1 :].splitlines()
    for index, line in enumerate(tail):
        line = line.strip()
        following = tail[index + 1] if index + 1 < len(tail) else ""
        if field_label(line, following) or (not line and values):
            break
        if line:
            # 多栏的原始文字还带有列间留白时，不能将两列值拼成一个地名。
            if re.search(r"\S(?:\t| {3,})\S", line):
                return ""
            values.append(line)
            if len(values) > MAX_PORT_LINES:
                return ""
    return port_lines(values)


def parse_bill(text):
    """返回 {bl_no, port_of_loading, port_of_discharge, on_board_date}；缺失项为空字符串 / None。"""
    upper = (text or "").upper()
    label = _BL_LABEL.search(upper)
    shapes = _BL_SHAPE.findall(upper)
    on_board = _ON_BOARD.search(upper)
    return {
        "bl_no": label.group(1) if label else (max(shapes, key=len) if shapes else ""),
        "port_of_loading": _port(upper, r"PORT\s+OF\s+LOADING"),
        "port_of_discharge": _port(upper, r"PORT\s+OF\s+DISCHARGE"),
        "on_board_date": parse_date(on_board.group(1)) if on_board else None,
    }


def missing_fields(bill):
    """资料包要求提单具备的字段中仍缺的项（中文名）。"""
    labels = (
        ("bl_no", "提单号"),
        ("port_of_loading", "装运口岸"),
        ("port_of_discharge", "目的口岸"),
        ("on_board_date", "装船日期"),
    )
    return [label for field, label in labels if not bill.get(field)]


def english_date(value):
    """合同签订日期写法：9th Apr 2026。"""
    suffix = "th" if 10 <= value.day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(value.day % 10, "th")
    return f"{value.day}{suffix} {datetime(value.year, value.month, 1):%b} {value.year}"


def retry_values(saved, parsed):
    """重复上传相同提单时仅补空字段，保留已有识别值及人工核对结果。"""
    fields = ("bl_no", "port_of_loading", "port_of_discharge", "on_board_date")
    return {field: parsed[field] for field in fields if not saved[field] and parsed[field]}
