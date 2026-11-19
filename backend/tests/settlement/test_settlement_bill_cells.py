"""扫描提单表格栏位复识：按网格找范围，两个局部识别结果一致才采用。"""

from datetime import date

import pytest
from backend.modules.settlement.policy.bill_layout_policy import agreed, parse_words
from backend.modules.settlement.service.bill_ocr_cells import cell_box, refine_cells
from backend.tests.settlement.test_settlement_bill_ocr import words
from PIL import Image, ImageDraw


def table_image():
    image = Image.new("L", (1600, 800), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 100, 1400, 230), outline=0, width=3)
    # 扫描线的小缺口不应把右边界截断在字段值之前。
    draw.rectangle((800, 99, 810, 104), fill=255)
    draw.rectangle((900, 226, 910, 231), fill=255)
    return image


@pytest.mark.parametrize(
    "field,label,value,expected",
    [
        ("port_of_loading", "Port of Loading", "SHANGHAI", "SHANGHAI"),
        ("port_of_discharge", "Port of Discharge", "TEST HARBOR, COUNTRY", "TEST HARBOR, COUNTRY"),
        ("on_board_date", "On Board Date", "2026.11.01", date(2026, 11, 1)),
    ],
)
def test_cell_reading_recovers_missing_label_in_other_page_mode(field, label, value, expected):
    image = table_image()
    readings = [words([(220, 120, label)]), words([(20, 650, "Other text")])]
    calls = []

    def read(crop, mode):
        assert crop.width > 1500  # 完整栏位，不能截断长港口名称。
        calls.append(mode)
        if field == "on_board_date":
            x, y = crop.width - 400, 40
        else:
            x, y = 40, 40
        output = words([(x, y, value)])
        # 裁剪图放大两倍；返回两倍字高，映射后仍为普通文字。
        return [dict(word, bottom=word["top"] + 48) for word in output]

    result = refine_cells(image, readings, read)
    assert calls == ["6", "7"]
    assert agreed([parse_words(reading) for reading in result])[field] == expected
    assert agreed([parse_words(reading) for reading in readings])[field] in ("", None)


@pytest.mark.parametrize("failed", [False, True])
def test_cell_disagreement_or_failure_does_not_replace_original(failed):
    readings = [words([(220, 120, "Port of Loading")])] * 2
    calls = []

    def read(crop, mode):
        calls.append(mode)
        if failed:
            return None
        return [
            dict(word, bottom=word["top"] + 48)
            for word in words([(40, 40, "TEST HARBOR" if mode == "6" else "OTHER HARBOR")])
        ]

    result = refine_cells(table_image(), readings, read)
    assert result is readings
    assert calls


def test_no_nearby_grid_does_not_guess_a_crop():
    image = Image.new("L", (1600, 800), 255)
    label = {"left": 220, "right": 450, "top": 120, "bottom": 144}
    assert cell_box(image, label, 24) is None


def test_top_field_label_wins_over_body_text_and_issue_date_is_not_onboard():
    body = words([(20, 650, "port of loading"), (20, 690, "or place of delivery")])
    fields = words([(220, 120, "Port of Loading"), (220, 165, "TEST HARBOR")])
    assert parse_words(body + fields)["port_of_loading"] == "TEST HARBOR"
    assert parse_words(body)["port_of_loading"] == ""
    layout = [
        (220, 120, "Place and Date of Issue 2026.11.09"),
        (220, 180, "On Board Date"),
        (1100, 180, "2026.11.01"),
    ]
    assert parse_words(words(layout))["on_board_date"] == date(2026, 11, 1)
    assert parse_words(words(layout[:-1]))["on_board_date"] is None


def test_date_cell_is_checked_even_if_whole_page_agrees_on_wrong_digit():
    labels = words([(220, 120, "On Board Date"), (1100, 120, "2026.11.04")])
    readings = [labels, labels]
    assert agreed([parse_words(row) for row in readings])["on_board_date"] == date(2026, 11, 4)

    def read(crop, mode):
        return [dict(word, bottom=word["top"] + 48) for word in words([(crop.width - 400, 40, "2026.11.01")])]

    result = refine_cells(table_image(), readings, read)
    assert agreed([parse_words(row) for row in result])["on_board_date"] == date(2026, 11, 1)
