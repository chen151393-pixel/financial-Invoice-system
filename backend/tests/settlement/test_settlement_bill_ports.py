"""提单口岸跨行：整栏提取、碎片回拼、相邻栏隔离与模型冲突保护。"""

from datetime import date

import pytest
from backend.modules.settlement.policy.bill_layout_policy import parse_words
from backend.modules.settlement.policy.bill_parse_policy import parse_bill
from backend.modules.settlement.service.bill_model_reader import BillModelReader
from backend.modules.settlement.service.bill_service import BillService
from backend.tests.settlement.documents_support import bill_pdf, scanned_bill_pdf
from backend.tests.settlement.test_settlement_bill_model import FakeExtractor
from backend.tests.settlement.test_settlement_bill_ocr import FakeOcr, words

DESTINATION = "LOS ANGELES, CA, UNITED STATES"
PORT_LINES = ("LOS", "ANGELES,C", "A,UN", "ITED", "STATES")


@pytest.mark.parametrize("label", ["PORT OF DISCHARGE", "PORT OF\nDISCHARGE"])
@pytest.mark.parametrize("inline", [False, True])
def test_text_port_collects_all_wrapped_lines_until_the_next_field(label, inline):
    separator = ": " if inline else "\n"
    text = (
        "PORT OF LOADING\nYANTIAN,\nCHINA\n"
        + label
        + separator
        + "\n".join(PORT_LINES)
        + "\nFINAL DESTINATION\nLONDON, UNITED KINGDOM\nCONTAINER NO.\nCAIU5852953\n"
    )
    parsed = parse_bill(text)
    assert parsed["port_of_loading"] == "YANTIAN, CHINA"
    assert parsed["port_of_discharge"] == DESTINATION


@pytest.mark.parametrize("tail", ["", "\nFINAL DESTINATION\nLONDON", "\n\nANGELES, CA"])
def test_isolated_los_is_not_accepted_as_a_complete_port(tail):
    assert parse_bill("PORT OF DISCHARGE:\nLOS" + tail)["port_of_discharge"] == ""


@pytest.mark.parametrize(
    "value",
    [
        "LOS\nANG3LES, CA",
        "LOS ANGELES,",
        "LOS\nANGELES,C",
        "LOS\nANGELES,C\nA,UN",
        "\n".join(["TEST"] * 10),
    ],
)
def test_invalid_or_unfinished_continuation_does_not_keep_the_first_line(value):
    assert parse_bill("PORT OF DISCHARGE:\n" + value)["port_of_discharge"] == ""


def test_plain_text_does_not_guess_parallel_columns_or_append_other_field_values():
    parallel = "PORT OF DISCHARGE    FINAL DESTINATION\nLOS ANGELES    LONDON\n"
    assert parse_bill(parallel)["port_of_discharge"] == ""
    normal = "PORT OF DISCHARGE:\nLOS ANGELES, CA\nCONTAINER NO.\nCAIU5852953\n"
    assert parse_bill(normal)["port_of_discharge"] == "LOS ANGELES, CA"
    assert parse_bill("PORT OF LOADING: PORT KLANG, MALAYSIA\n")["port_of_loading"] == "PORT KLANG, MALAYSIA"
    same_line = "PORT OF DISCHARGE: LOS ANGELES    LONDON\n"
    assert parse_bill(same_line)["port_of_discharge"] == ""
    split_heading = "PORT OF DISCHARGE\nLOS\nANGELES, CA\nNUMBER\nAND KIND OF PACKAGES\nCARTONS\n"
    assert parse_bill(split_heading)["port_of_discharge"] == "LOS ANGELES, CA"
    wrapped_next_label = "PORT OF DISCHARGE\nLOS ANGELES, CA\nPORT\nOF\nLOADING\nYANTIAN, CHINA\n"
    assert parse_bill(wrapped_next_label)["port_of_discharge"] == "LOS ANGELES, CA"
    assert parse_bill(wrapped_next_label)["port_of_loading"] == "YANTIAN, CHINA"
    wrapped_port_name = "PORT OF LOADING:\nPORT\nKLANG, MALAYSIA\n"
    assert parse_bill(wrapped_port_name)["port_of_loading"] == "PORT KLANG, MALAYSIA"


def port_layout(*, wrapped_label=False, value_lines=PORT_LINES, neighbor=900):
    headings = [(20, 100, "PORT OF DISCHARGE"), (neighbor, 100, "PORT OF LOADING")]
    start = 145
    if wrapped_label:
        headings = [(20, 100, "PORT OF"), (20, 130, "DISCHARGE"), (neighbor, 100, "PORT OF LOADING")]
        start = 175
    return words(
        headings
        + [(20, start + index * 30, text) for index, text in enumerate(value_lines)]
        + [
            (neighbor, 145, "YANTIAN, CHINA"),
            (20, start + len(value_lines) * 30, "CONTAINER NO."),
            (20, start + len(value_lines) * 30 + 35, "CAIU5852953"),
        ]
    )


@pytest.mark.parametrize("wrapped_label", [False, True])
@pytest.mark.parametrize("neighbor", [900, 360])
def test_ocr_reads_every_line_in_the_port_column_without_reading_its_neighbor(wrapped_label, neighbor):
    parsed = parse_words(port_layout(wrapped_label=wrapped_label, neighbor=neighbor))
    assert parsed["port_of_discharge"] == DESTINATION
    assert parsed["port_of_loading"] == "YANTIAN, CHINA"


def test_ocr_does_not_keep_a_fragment_or_cross_a_blank_gap():
    assert parse_words(port_layout(value_lines=("LOS",)))["port_of_discharge"] == ""
    layout = words([(20, 100, "PORT OF DISCHARGE"), (20, 145, "LOS"), (20, 400, "ANGELES, CA")])
    assert parse_words(layout)["port_of_discharge"] == ""
    uncertain_columns = words(
        [
            (20, 100, "PORT OF DISCHARGE"),
            (20, 145, "LOS"),
            (500, 145, "LONDON"),
        ]
    )
    assert parse_words(uncertain_columns)["port_of_discharge"] == ""


def test_ocr_stops_before_a_wide_following_header_even_when_its_text_crosses_columns():
    layout = words(
        [
            (20, 100, "PORT OF DISCHARGE"),
            (360, 100, "PORT OF LOADING"),
            (20, 145, "LOS"),
            (20, 175, "ANGELES, CA"),
            (360, 145, "YANTIAN, CHINA"),
            (20, 205, "NUMBER AND KIND OF PACKAGES"),
        ]
    )
    assert parse_words(layout)["port_of_discharge"] == "LOS ANGELES, CA"
    wrapped_name = port_layout(value_lines=("PORT", "KLANG, MALAYSIA"))
    assert parse_words(wrapped_name)["port_of_discharge"] == "PORT KLANG, MALAYSIA"


@pytest.mark.parametrize("model_port", [DESTINATION, "LONDON, UNITED KINGDOM"])
def test_real_text_pdf_no_longer_creates_a_false_conflict_but_real_conflicts_stay_blank(model_port):
    # 缺少提单号，确保模型确实会调用；目的口岸必须先由本地规则完整提取。
    content = bill_pdf(
        (
            "PORT OF LOADING: YANTIAN, CHINA",
            "PORT OF DISCHARGE:",
            *PORT_LINES,
            "ON BOARD DATE: FEB 04 2026",
        )
    )
    extractor = FakeExtractor(
        {
            "bl_no": "C2613601508",
            "port_of_loading": "YANTIAN, CHINA",
            "port_of_discharge": model_port,
            "on_board_date": "2026-02-04",
        }
    )
    reader = BillService(None, None, None, model=BillModelReader(extractor))
    parsed, note = reader._parse(content)
    assert len(extractor.calls) == 1
    assert parsed["bl_no"] == "C2613601508" and parsed["on_board_date"] == date(2026, 2, 4)
    if model_port == DESTINATION:
        assert parsed["port_of_discharge"] == DESTINATION
        assert "不一致" not in note and "目的口岸" not in note
    else:
        assert parsed["port_of_discharge"] == ""
        assert "不一致" in note and "目的口岸" in note


def test_scanned_pdf_uses_the_same_multiline_port_rule():
    layout = port_layout()
    parsed, note = BillService(None, None, None, ocr=FakeOcr([layout, layout]))._parse(scanned_bill_pdf())
    assert parsed["port_of_discharge"] == DESTINATION
    assert "目的口岸" not in note and "扫描件由系统识别" in note
