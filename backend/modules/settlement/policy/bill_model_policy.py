"""识别模型给出的提单字段：提示词、返回值校验、与本地规则结果的合并（纯函数）。

模型可能认错字或答非所问，因此：
- 返回值逐字段校验格式，不合格的当作没识别到；
- 只用来补本地规则留空的字段；
- 本地规则与模型都给出值但不一致的字段留空，由人工对照原件填写。
"""

import re
from datetime import date

from .bill_layout_policy import FIELDS, port_value

# 提单为英文单据，提示词用英文；要求认不出就留空，不得猜测。
INSTRUCTIONS = """You extract four fields from an ocean bill of lading or sea waybill.
Reply with one JSON object and nothing else, with exactly these keys:
- "bl_no": the bill of lading number exactly as printed, including any carrier prefix, without spaces.
  It is not the booking number and not a container number.
- "port_of_loading": the text printed in the "Port of Loading" box, in upper case.
  It is not the place of receipt.
- "port_of_discharge": the text printed in the "Port of Discharge" box, in upper case.
  It is not the place of delivery.
- "on_board_date": the shipped / laden on board date as YYYY-MM-DD. It is not the issue date.
Copy characters exactly as printed. If a field is missing, unclear, or you are not sure,
use an empty string for it. Never guess."""

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _bl_no(value):
    number = re.sub(r"\s", "", _text(value)).upper()
    valid = re.fullmatch(r"[A-Z0-9]{6,20}", number) and any(char.isdigit() for char in number)
    return number if valid else ""


def _date(value):
    text = _text(value)
    if not _ISO_DATE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def clean(answer):
    """把模型返回的对象整理成与 parse_bill 相同的字段；格式不合格的字段为空。"""
    answer = answer if isinstance(answer, dict) else {}
    return {
        "bl_no": _bl_no(answer.get("bl_no")),
        "port_of_loading": port_value(_text(answer.get("port_of_loading"))),
        "port_of_discharge": port_value(_text(answer.get("port_of_discharge"))),
        "on_board_date": _date(answer.get("on_board_date")),
    }


def _same(left, right):
    """比较时忽略大小写、空格与标点，避免 NINGBO,CHINA 与 NINGBO, CHINA 被当作不一致。"""
    if isinstance(left, date) or isinstance(right, date):
        return left == right
    return re.sub(r"[^A-Z0-9]", "", left.upper()) == re.sub(r"[^A-Z0-9]", "", right.upper())


def merge(ruled, modeled):
    """返回 (字段, 采用了模型值的字段名, 两边不一致而留空的字段名)。"""
    merged, taken, conflicts = {}, [], []
    for field in FIELDS:
        mine, theirs = ruled[field], modeled[field]
        if mine and theirs and not _same(mine, theirs):
            merged[field] = None if field == "on_board_date" else ""
            conflicts.append(field)
        elif mine or not theirs:
            merged[field] = mine
        else:
            merged[field] = theirs
            taken.append(field)
    return merged, taken, conflicts
