"""按实际表格边界裁剪港口、装船日期栏复识，不用船公司或客户固定坐标。"""

import re

from PIL import ImageOps

from ..policy.bill_layout_policy import agreed, cell_labels, parse_words


def cell_box(image, label, height):
    """取包围标签的横线与竖线；找不到完整且邻近的栏位时放弃。"""
    width = image.width
    pixels = image.tobytes()
    pattern = re.compile(b"\x00{" + str(max(50, width // 30)).encode() + b",}")
    center = (label["left"] + label["right"]) / 2
    above, below = [], []
    start = max(0, int(label["top"] - 6 * height))
    end = min(image.height, int(label["bottom"] + 6 * height))
    for y in range(start, end):
        if label["top"] <= y <= label["bottom"]:
            continue
        for match in pattern.finditer(pixels[y * width : (y + 1) * width]):
            if match.start() < center < match.end():
                (above if y < label["top"] else below).append((y, match.start(), match.end()))
    if not above or not below:
        return None
    top = max(above)[0]
    bottom = min(below)[0]

    def span_at(y):
        # 扫描横线可能断开或倾斜，合并邻近几行中仅有小间隙的线段。
        spans = sorted(
            (match.start(), match.end())
            for row in range(max(0, y - 3), min(image.height, y + 4))
            for match in pattern.finditer(pixels[row * width : (row + 1) * width])
        )
        merged = []
        for left, right in spans:
            if merged and left - merged[-1][1] <= height:
                merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
            else:
                merged.append((left, right))
        return next((span for span in merged if span[0] < center < span[1]), None)

    top_span, bottom_span = span_at(top), span_at(bottom)
    if top_span is None or bottom_span is None:
        return None
    left_top, right_top = top_span
    left_bottom, right_bottom = bottom_span
    left, right = max(left_top, left_bottom), min(right_top, right_bottom)
    if bottom - top < height or left >= label["left"] or right <= label["right"]:
        return None
    # 竖线须贯穿本栏的大部分高度，避免将文字笔画当作边界。
    columns = [
        x
        for x in range(left, right)
        if sum(pixels[y * width + x] == 0 for y in range(top, bottom + 1)) >= (bottom - top + 1) * 0.85
    ]
    left = max((x for x in columns if x < label["left"]), default=left)
    right = min((x for x in columns if x > label["right"]), default=right)
    return left, top, right, bottom


def refine_cells(image, readings, read_words):
    parsed = agreed([parse_words(words) for words in readings])
    refined = set()
    for field, label, height, source in cell_labels(readings):
        # 日期即使整页结果一致也复核，表格线可能使两次都把 1 误读为 4。
        if field in refined or (parsed[field] and field != "on_board_date"):
            continue
        box = cell_box(image, label, height)
        if box is None:
            continue
        left, top, right, bottom = box
        value_box = (
            (label["right"] + 3, top + 4, right - 4, bottom - 4)
            if field == "on_board_date"
            else (left + 4, label["bottom"] + 3, right - 4, bottom - 4)
        )
        if value_box[2] <= value_box[0] or value_box[3] <= value_box[1]:
            continue
        crop = image.crop(value_box)
        crop = ImageOps.expand(crop.resize((crop.width * 2, crop.height * 2)), border=20, fill="white")
        labels = [
            word
            for word in source
            if label["left"] <= word["left"] < label["right"]
            and label["top"] <= word["top"] <= label["bottom"]
        ]
        replacements = []
        for mode in ("6", "7"):
            words = read_words(crop, mode)
            if not words:
                break
            replacements.append(
                labels
                + [
                    dict(
                        word,
                        left=(word["left"] - 20) / 2 + value_box[0],
                        right=(word["right"] - 20) / 2 + value_box[0],
                        top=(word["top"] - 20) / 2 + value_box[1],
                        bottom=(word["bottom"] - 20) / 2 + value_box[1],
                    )
                    for word in words
                ]
            )
        if len(replacements) != 2:
            continue
        value = agreed([parse_words(words) for words in replacements])[field]
        if not value:
            continue
        readings = [
            [word for word in words if not (left <= word["left"] < right and top <= word["top"] < bottom)]
            + replacements[i % 2]
            for i, words in enumerate(readings)
        ]
        refined.add(field)
        parsed = agreed([parse_words(words) for words in readings])
    return readings
