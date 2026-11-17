"""提单文字解析（纯函数）：从 PDF 文字中尽力识别提单号、装运口岸、目的口岸与装船日期。

各船公司版式不同，识别不到的字段留空，由人工在页面补填；本模块不做任何默认值或猜测港口。
"""

import re
from datetime import date, datetime

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
_PORT_VALUE = r"([A-Z][A-Z .,'()/-]{2,60})"


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


_OTHER_LABEL = re.compile(r"PORT OF|PLACE OF|VESSEL|VOYAGE|PRE-CARRIAGE|DELIVERY")


def _port(upper, label):
    """标签同一行冒号后的值，或标签下一行的值。

    多个标签并排成一行时，下一行的值属于哪一列无法从文字判断，一律放弃，留给人工填写。
    """
    same = re.search(label + r"\s*[:：]\s*" + _PORT_VALUE, upper)
    below = re.search(r"^([^\n]*)" + label + r"([^\n]*)\n\s*" + _PORT_VALUE, upper, re.M)
    candidates = [same.group(1)] if same else []
    if below and not _OTHER_LABEL.search(below.group(1) + below.group(2)):
        candidates.append(below.group(3))
    for candidate in candidates:
        value = re.sub(r"\s+", " ", candidate).strip(" ,.-/")
        if value and not _OTHER_LABEL.search(value):
            return value[:200]
    return ""


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
