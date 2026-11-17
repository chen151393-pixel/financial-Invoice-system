"""扫描件提单的版面解析（纯函数）：按“标签下方 / 右侧同一栏”的位置关系取值。

输入是 OCR 给出的带坐标文字。扫描识别会认错字符，因此：
- 只按版面位置取值，不猜测港口，取不到就留空；
- 同一页用多种识别方式各解析一次，结果一致的字段才采用（见 agreed）；
- 装船日期若同时印有数字写法与英文序数写法（OBD: NOVEMBER TWELFTH, 2026），两者必须一致。
"""

import re
from datetime import date
from statistics import median

from .bill_parse_policy import parse_date

FIELDS = ("bl_no", "port_of_loading", "port_of_discharge", "on_board_date")
_MONTHS = ("JANUARY FEBRUARY MARCH APRIL MAY JUNE JULY AUGUST SEPTEMBER OCTOBER NOVEMBER DECEMBER").split()
_ORDINALS = (
    "FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH TWELFTH THIRTEENTH "
    "FOURTEENTH FIFTEENTH SIXTEENTH SEVENTEENTH EIGHTEENTH NINETEENTH TWENTIETH TWENTY-FIRST "
    "TWENTY-SECOND TWENTY-THIRD TWENTY-FOURTH TWENTY-FIFTH TWENTY-SIXTH TWENTY-SEVENTH TWENTY-EIGHTH "
    "TWENTY-NINTH THIRTIETH THIRTY-FIRST"
).split()
_WORDED_DATE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+([A-Z]+(?:\s*-\s*[A-Z]+)?)\s*,?\s*(\d{4})\b")
_PORT = re.compile(r"[A-Z][A-Z .,'()/-]{2,60}")
_LABEL_WORDS = re.compile(r"\b(PORT|PLACE|VESSEL|VOYAGE|CARRIAGE|DELIVERY|RECEIPT|DESTINATION|ROUTING)\b")


def _key(text):
    """标签比较用：去掉标点（保留 /），大写。"""
    return re.sub(r"[^A-Z0-9/]", "", text.upper())


def _same_row(a, b, height):
    return abs(a["top"] - b["top"]) < 0.7 * height


def _find_label(words, tokens, height):
    """返回标签外框 {left, right, top, bottom}；标签各词须在同一行且相邻。"""
    for word in words:
        if _key(word["text"]) != tokens[0]:
            continue
        chain = [word]
        for token in tokens[1:]:
            last = chain[-1]
            following = [
                other
                for other in words
                if _key(other["text"]) == token
                and _same_row(other, last, height)
                and 0 <= other["left"] - last["right"] < 2 * height
            ]
            if not following:
                break
            chain.append(min(following, key=lambda other: other["left"]))
        else:
            return {
                "left": chain[0]["left"],
                "right": chain[-1]["right"],
                "top": min(item["top"] for item in chain),
                "bottom": max(item["bottom"] for item in chain),
            }
    return None


def _column(words, label, height):
    """标签所在栏的取值：(标签右侧同一行的词, 标签正下方最近一行的词)。

    栏的右边界是同一行上与标签相隔较远（超过 6 个字高）的下一个词（即右侧相邻栏的标签）。
    """
    row = [word for word in words if _same_row(word, label, height) and word["left"] >= label["right"]]
    far = [word["left"] for word in row if word["left"] - label["right"] > 6 * height]
    limit = min(far) - height if far else float("inf")
    beside = [word for word in row if word["left"] < limit]
    under = [
        word
        for word in words
        if 0.6 * height < word["top"] - label["top"] and word["top"] - label["bottom"] < 3 * height
        if label["left"] - 3 * height <= word["left"] < limit
    ]
    if under:
        nearest = min(under, key=lambda word: word["top"])
        under = [word for word in under if _same_row(word, nearest, height)]
    return _join(beside), _join(under)


def _join(words):
    return " ".join(word["text"] for word in sorted(words, key=lambda word: word["left"])).strip()


def _port(words, tokens, height):
    label = _find_label(words, tokens, height)
    if not label:
        return ""
    value = re.sub(r"\s*,\s*", ", ", _column(words, label, height)[1].upper())
    value = re.sub(r"\s+", " ", value).strip(" ,.-/*")
    if not _PORT.fullmatch(value) or _LABEL_WORDS.search(value):
        return ""
    return value


def _number(text):
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _is_bl(value, low, high):
    return bool(re.fullmatch(rf"[A-Z0-9]{{{low},{high}}}", value)) and any(char.isdigit() for char in value)


def _bl_no(words, height):
    label = _find_label(words, ["B/L", "NO"], height)
    if not label:
        return ""
    beside, under = (_number(part) for part in _column(words, label, height))
    if _is_bl(beside, 8, 20):
        return beside
    # 船公司代码印在标签旁、号码印在下一行（如 HMM：HDMU + SHAZK7P55100）
    if re.fullmatch(r"[A-Z]{4}", beside) and _is_bl(under, 6, 16):
        return beside + under
    if not beside and _is_bl(under, 8, 20):
        return under
    return ""


def _worded_date(words):
    text = " ".join(word["text"] for word in sorted(words, key=lambda word: (word["top"], word["left"])))
    for month, ordinal, year in _WORDED_DATE.findall(text.upper()):
        ordinal = re.sub(r"\s", "", ordinal)
        if ordinal not in _ORDINALS:
            continue
        try:
            return date(int(year), _MONTHS.index(month) + 1, _ORDINALS.index(ordinal) + 1)
        except ValueError:
            continue
    return None


def _on_board_date(words, height):
    label = _find_label(words, ["ON", "BOARD", "DATE"], height)
    if not label:
        return None
    beside, under = _column(words, label, height)
    printed = parse_date(beside) or parse_date(under)
    # 英文序数写法只在标签附近的几行内查找，避免取到签发日期等其他日期
    nearby = [word for word in words if 0 <= word["top"] - label["top"] < 6 * height]
    worded = _worded_date(nearby)
    if printed and worded and printed != worded:
        return None
    return printed or worded


def parse_words(words):
    """words：[{text, left, top, right, bottom}]（同一页、同一坐标系）。返回与 parse_bill 相同的字段。"""
    words = [word for word in words if word["text"].strip()]
    if not words:
        return {"bl_no": "", "port_of_loading": "", "port_of_discharge": "", "on_board_date": None}
    height = median(word["bottom"] - word["top"] for word in words)
    return {
        "bl_no": _bl_no(words, height),
        "port_of_loading": _port(words, ["PORT", "OF", "LOADING"], height),
        "port_of_discharge": _port(words, ["PORT", "OF", "DISCHARGE"], height),
        "on_board_date": _on_board_date(words, height),
    }


def agreed(results):
    """多次识别的结果逐字段比对：全部一致且非空才采用，否则留空由人工填写。"""
    merged = {}
    for field in FIELDS:
        values = [result[field] for result in results]
        same = bool(values) and all(value == values[0] for value in values)
        merged[field] = values[0] if same and values[0] else ("" if field != "on_board_date" else None)
    return merged
