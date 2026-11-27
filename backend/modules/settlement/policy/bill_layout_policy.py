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
from .bill_port_policy import field_head, field_label, port_lines

FIELDS = ("bl_no", "port_of_loading", "port_of_discharge", "on_board_date")
_MONTHS = ("JANUARY FEBRUARY MARCH APRIL MAY JUNE JULY AUGUST SEPTEMBER OCTOBER NOVEMBER DECEMBER").split()
_ORDINALS = (
    "FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH TWELFTH THIRTEENTH "
    "FOURTEENTH FIFTEENTH SIXTEENTH SEVENTEENTH EIGHTEENTH NINETEENTH TWENTIETH TWENTY-FIRST "
    "TWENTY-SECOND TWENTY-THIRD TWENTY-FOURTH TWENTY-FIFTH TWENTY-SIXTH TWENTY-SEVENTH TWENTY-EIGHTH "
    "TWENTY-NINTH THIRTIETH THIRTY-FIRST"
).split()
_WORDED_DATE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+([A-Z]+(?:\s*-\s*[A-Z]+)?)\s*,?\s*(\d{4})\b")


def _key(text):
    """标签比较用：去掉标点（保留 /），大写。"""
    return re.sub(r"[^A-Z0-9/]", "", text.upper())


def _same_row(a, b, height):
    return abs(a["top"] - b["top"]) < 0.7 * height


def _find_label(words, tokens, height, *, wrapped=False):
    """返回标签外框；口岸标签额外允许紧邻、左对齐的折行，不跨到旁边栏位。"""
    for word in sorted(words, key=lambda item: (item["top"], item["left"])):
        if _key(word["text"]) != tokens[0]:
            continue
        chain = [word]
        for token in tokens[1:]:
            last = chain[-1]
            following = [
                other
                for other in words
                if _key(other["text"]) == token
                and (
                    (_same_row(other, last, height) and 0 <= other["left"] - last["right"] < 2 * height)
                    or (
                        wrapped
                        and 0 <= other["top"] - last["bottom"] < height
                        and abs(other["left"] - chain[0]["left"]) < height
                    )
                )
            ]
            if not following:
                break
            chain.append(min(following, key=lambda other: (other["top"], other["left"])))
        else:
            return {
                "left": min(item["left"] for item in chain),
                "right": max(item["right"] for item in chain),
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
    headings = [word for word in words if _key(word["text"]) != "PORT" or word["text"][:1].isupper()]
    label = _find_label(headings, tokens, height, wrapped=True)
    if not label:
        return ""
    # 复用原列边界口径，值按从上到下的连续行读取，而非只保留最近一行。
    neighbors = [
        word["left"]
        for word in words
        if label["top"] - height * 0.5 <= word["top"] <= label["bottom"]
        and word["left"] - label["right"] > 0.5 * height
        and (field_head(word["text"]) or word["left"] - label["right"] > 6 * height)
    ]
    right = min(neighbors) - height * 0.5 if neighbors else float("inf")
    below = sorted(
        (
            word
            for word in words
            if word["top"] >= label["bottom"] + height * 0.3
            and label["left"] - 3 * height <= word["left"] < right
        ),
        key=lambda word: (word["top"], word["left"]),
    )
    rows = []
    for word in below:
        if not rows or not _same_row(rows[-1][0], word, height):
            rows.append([])
        rows[-1].append(word)
    lines, bottom = [], label["bottom"]
    for index, row in enumerate(rows):
        value = _join(row)
        following = _join(rows[index + 1]) if index + 1 < len(rows) else ""
        if field_label(value, following) or min(item["top"] for item in row) - bottom > 1.5 * height:
            break
        if any(item["right"] > right for item in row):
            return ""
        row = sorted(row, key=lambda item: item["left"])
        if any(second["left"] - first["right"] > 6 * height for first, second in zip(row, row[1:])):
            return ""
        lines.append(value)
        bottom = max(item["bottom"] for item in row)
    return port_lines(lines)


def _number(text):
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _is_bl(value, low, high):
    return bool(re.fullmatch(rf"[A-Z0-9]{{{low},{high}}}", value)) and any(char.isdigit() for char in value)


def _bl_label(words, height):
    return _find_label(words, ["B/L", "NO"], height) or _find_label(
        words, ["BILL", "OF", "LADING", "NO"], height
    )


def bl_value_words(readings):
    """定位多次识别中同一提单号词框，供局部复识；不使用订舱号或跨栏的文字。"""
    targets = []
    for words in readings:
        if not words:
            return []
        height = median(word["bottom"] - word["top"] for word in words)
        label = _bl_label(words, height)
        if not label:
            return []
        row = sorted(
            (
                word
                for word in words
                if _same_row(word, label, height) and word["left"] >= label["right"] and _key(word["text"])
            ),
            key=lambda word: word["left"],
        )
        if not row or row[0]["left"] - label["right"] > 12 * height:
            return []
        target = row[0]
        if not _is_bl(_number(target["text"]), 8, 20):
            return []
        if targets and any(
            abs(target[key] - targets[0][key]) > height for key in ("left", "top", "right", "bottom")
        ):
            return []
        targets.append(target)
    return targets if len(targets) >= 2 else []


def _bl_no(words, height):
    label = _bl_label(words, height)
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
    # 同行日期与标签之间可能有较大留白，不能把日期本身误作下一栏标签。
    row = sorted(
        (
            word
            for word in words
            if _same_row(word, label, height) and word["left"] >= label["right"] and _key(word["text"])
        ),
        key=lambda word: word["left"],
    )
    inline = None
    if row:
        token = row[0]["text"].upper()
        # 只在明确日期的日字段修复 O/0，绝不替换提单号中的字母。
        if re.fullmatch(r"[0-9O]{1,2}-[A-Z]{3}-[0-9]{4}", token):
            day, month, year = token.split("-")
            inline = parse_date(f"{day.replace('O', '0')}-{month}-{year}")
        elif re.fullmatch(r"[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2}", token):
            inline = parse_date(token)
    printed = inline or parse_date(beside) or parse_date(under)
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


def cell_labels(readings):
    """待局部复识的栏位标签；排除正文中的小写 port of loading 等合同条款。"""
    tokens = {
        "port_of_loading": ["PORT", "OF", "LOADING"],
        "port_of_discharge": ["PORT", "OF", "DISCHARGE"],
        "on_board_date": ["ON", "BOARD", "DATE"],
    }
    candidates = []
    for words in readings:
        if not words:
            continue
        height = median(word["bottom"] - word["top"] for word in words)
        headings = [
            word for word in words if word["text"][:1].isupper() or _key(word["text"]) not in ("PORT", "ON")
        ]
        for field, label_tokens in tokens.items():
            label = _find_label(headings, label_tokens, height, wrapped=field != "on_board_date")
            if label:
                candidates.append((field, label, height, words))
    return candidates
