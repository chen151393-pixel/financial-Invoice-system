"""提单扫描件：版面解析规则、多次识别结果比对、上传流程中的识别与人工核对。"""

import io
import shutil
import subprocess
from datetime import date
from types import SimpleNamespace

import pytest
from backend.modules.settlement.dto.bill_dto import UpdateBillRequest
from backend.modules.settlement.policy.bill_layout_policy import agreed, parse_words
from backend.modules.settlement.service.bill_ocr import BillOcr, page_image, words_from_tsv
from backend.modules.settlement.service.bill_ocr_refine import refine_bl
from backend.tests.settlement.documents_support import Documents, bill_pdf, scanned_bill_pdf
from backend.tests.settlement.test_settlement_batches import create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from PIL import Image

# 仿船公司格式提单的栏位布局（300dpi 像素坐标）：标签在上、值在下，多栏并排；内容为虚构。
# 提单号特意不含 0 / O 这类扫描识别容易混淆的字符：混淆时多次识别会一致地认错，只能靠人工核对。
LAYOUT = (
    (1290, 330, "Booking No."),
    (1290, 365, "TESTBK7P00001"),
    (1805, 330, "B/L No."),
    (1955, 330, "TSTU"),
    (1945, 365, "SHATEST58231"),
    (240, 1240, "Pre-Carriage by"),
    (900, 1240, "Place of Receipt *"),
    (900, 1275, "NINGBO, CHINA"),
    (1640, 1240, "Port of Discharge"),
    (1640, 1275, "SANTOS, BRAZIL"),
    (240, 1325, "Ocean Vessel / Voyage / Flag"),
    (250, 1360, "TEST JADE V 0002W"),
    (900, 1325, "Port of Loading"),
    (900, 1360, "NINGBO, CHINA"),
    (1640, 1325, "Place of Delivery *"),
    (1640, 1360, "SANTOS, BRAZIL"),
    (1240, 3025, "Number of Original B(s)/L"),
    (1240, 3060, "THREE (3)"),
    (1760, 3025, "On Board Date"),
    (1760, 3060, "NOV. 12, 2026"),
    (1580, 3105, "(OBD: NOVEMBER TWELFTH, 2026)"),
    (1320, 3150, "Dated at NINGBO, CHINA NOV. 14, 2026"),
)
EXPECTED = {
    "bl_no": "TSTUSHATEST58231",
    "port_of_loading": "NINGBO, CHINA",
    "port_of_discharge": "SANTOS, BRAZIL",
    "on_board_date": date(2026, 11, 12),
}


def words(layout=LAYOUT, replace=None):
    """把整行文字拆成带坐标的词，等同于 OCR 的输出（每个字符按 17 像素宽估算）。"""
    result = []
    for x, y, text in layout:
        text = (replace or {}).get(text, text)
        for word in text.split():
            width = len(word) * 17
            result.append({"text": word, "left": x, "top": y, "right": x + width, "bottom": y + 24})
            x += width + 12
    return result


def test_layout_takes_values_under_labels_in_the_same_column():
    assert parse_words(words()) == EXPECTED
    # 提单号整串印在标签右侧
    beside = [row for row in LAYOUT if row[2] not in ("TSTU", "SHATEST58231")] + [
        (1955, 330, "EGLV142503975412")
    ]
    assert parse_words(words(beside))["bl_no"] == "EGLV142503975412"
    assert parse_words([]) == {
        "bl_no": "",
        "port_of_loading": "",
        "port_of_discharge": "",
        "on_board_date": None,
    }


def test_layout_leaves_doubtful_fields_blank():
    # 数字写法与英文序数写法不一致：不取装船日期
    conflict = parse_words(words(replace={"NOV. 12, 2026": "NOV. 17, 2026"}))
    assert conflict["on_board_date"] is None and conflict["bl_no"] == EXPECTED["bl_no"]
    # 只有英文序数写法能读出时采用它；签发日期（Dated at）不当作装船日期
    worded = parse_words(words(replace={"NOV. 12, 2026": "N0V. I2, 2O26"}))
    assert worded["on_board_date"] == date(2026, 11, 12)
    neither = parse_words(words(replace={"NOV. 12, 2026": "", "(OBD: NOVEMBER TWELFTH, 2026)": ""}))
    assert neither["on_board_date"] is None
    # 口岸栏读到的不是地名（含数字）时留空
    assert parse_words(words(replace={"SANTOS, BRAZIL": "8ANT05, BRAZIL"}))["port_of_discharge"] == ""
    # 两次识别不一致的字段不采用
    other = dict(EXPECTED, port_of_loading="NINGB0, CHINA", bl_no="")
    merged = agreed([EXPECTED, other])
    assert merged == dict(EXPECTED, port_of_loading="", bl_no="")
    assert agreed([EXPECTED, EXPECTED]) == EXPECTED


def test_tsv_words_and_non_scanned_pdf():
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    tsv = "\n".join(
        (header, "4\t1\t1\t1\t1\t0\t10\t20\t300\t30\t-1\t", "5\t1\t1\t1\t1\t1\t10\t20\t80\t30\t96\tPort")
    )
    assert words_from_tsv(tsv) == [{"text": "Port", "left": 10, "top": 20, "right": 90, "bottom": 50}]
    # 有文字层的 PDF 没有整页图像；损坏的文件同样不识别
    assert page_image(bill_pdf()) is None and page_image(b"%PDF-broken") is None
    assert not BillOcr("").available and BillOcr("").readings(scanned_bill_pdf()) == []
    assert BillOcr("no-such-ocr-command").readings(scanned_bill_pdf()) == []


class FakeOcr:
    def __init__(self, readings):
        self.result = readings

    def readings(self, content):
        return self.result


def test_scanned_bill_is_recognized_then_confirmed_by_operator(seeded, tmp_path):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "985.50", fee="15.00")
    garbled = words(replace={"SANTOS, BRAZIL": "SANT0S, BRAZIL"})
    documents = Documents(seeded, tmp_path, FakeOcr([words(), garbled]))

    bill = documents.upload(batch.id, content=scanned_bill_pdf()).bills[0]
    assert (bill.blNo, bill.portOfLoading, bill.onBoardDate) == (
        "TSTUSHATEST58231",
        "NINGBO, CHINA",
        "2026-11-12",
    )
    # 两次识别不一致的目的口岸留空；识别结果提示人工核对
    assert bill.portOfDischarge == "" and bill.missing == ["目的口岸"]
    assert "目的口岸" in bill.parseNote and "对照原件核对" in bill.parseNote

    body = UpdateBillRequest(
        blNo=bill.blNo,
        portOfLoading=bill.portOfLoading,
        portOfDischarge="SANTOS, BRAZIL",
        onBoardDate="2026-11-12",
        declarationNos=bill.declarationNos,
    )
    confirmed = documents.bills.update(batch.id, bill.id, body, "finance-user").bills[0]
    assert confirmed.missing == [] and confirmed.parseNote == ""

    # 有文字层的提单不走识别
    text_bill = documents.upload(batch.id).bills[1]
    assert text_bill.blNo == "EGLV142503975412" and text_bill.parseNote == ""

    # 未安装识别程序：扫描件字段全部留空，由人工填写
    plain = Documents(seeded, tmp_path, FakeOcr([]))
    blank = plain.upload(batch.id, content=scanned_bill_pdf(((100, 100, "X"),))).bills[2]
    assert len(blank.missing) == 4 and "人工填写" in blank.parseNote and "核对" not in blank.parseNote


@pytest.mark.skipif(not shutil.which("tesseract"), reason="本机未安装 tesseract")
def test_real_tesseract_reads_a_scanned_layout():
    readings = BillOcr().readings(scanned_bill_pdf(LAYOUT))
    assert len(readings) == 2
    assert agreed([parse_words(reading) for reading in readings]) == EXPECTED


# 长标签、同一行留白较大的日期，签发日期与装船日期故意不同。
INLINE_LAYOUT = (
    (100, 100, "Bill of Lading No."),
    (450, 100, "ABCD12345678"),
    (100, 150, "Booking No. OTHER98765432"),
    (100, 940, "PLACE & DATE OF ISSUE: PORT, 09-NOV-2026"),
    (100, 1000, "SHIPPED ON BOARD DATE:"),
    (700, 1000, "O7-NOV-2026"),
)


def test_inline_long_label_and_spaced_onboard_date():
    parsed = parse_words(words(INLINE_LAYOUT))
    assert parsed["bl_no"] == "ABCD12345678"
    assert parsed["on_board_date"] == date(2026, 11, 7)
    without_values = [row for row in INLINE_LAYOUT if row[2] not in ("ABCD12345678", "O7-NOV-2026")]
    missing = parse_words(words(without_values))
    assert missing["bl_no"] == "" and missing["on_board_date"] is None
    # 局部字符纠正严格限制在日期中；提单号的 O 不转为零。
    assert parse_words(words(INLINE_LAYOUT, {"ABCD12345678": "ABCO12345678"}))["bl_no"] == "ABCO12345678"


@pytest.mark.parametrize(
    "outputs",
    [
        (b"ABCD12345678", b"ABCD12345678"),
        (b"ABCD12345678", b"ABCD12345679"),
        (b"", b""),
        (b"ABCD12345678\nOTHER123456", b""),
    ],
)
def test_focused_ocr_requires_agreement_and_keeps_other_fields(monkeypatch, outputs):
    readings = [words(INLINE_LAYOUT), words(INLINE_LAYOUT, {"ABCD12345678": "A8CD12345678"})]
    calls = []

    def run(command, **kwargs):
        crop = Image.open(io.BytesIO(kwargs["input"]))
        assert crop.width < 800 and crop.height < 200
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=outputs[len(calls) - 1])

    monkeypatch.setattr("backend.modules.settlement.service.bill_ocr_refine.subprocess.run", run)
    result = refine_bl(Image.new("L", (1000, 1200), "white"), readings, "tesseract")
    merged = agreed([parse_words(reading) for reading in result])
    assert merged["on_board_date"] == date(2026, 11, 7)
    assert readings[1] != readings[0]  # 不原地改写原始识别结果。
    if outputs[0] == outputs[1] and outputs[0]:
        assert merged["bl_no"] == "ABCD12345678" and len(calls) == 2
    else:
        assert merged["bl_no"] == ""


def test_focused_ocr_failure_preserves_original_readings(monkeypatch):
    readings = [words(INLINE_LAYOUT), words(INLINE_LAYOUT, {"ABCD12345678": "A8CD12345678"})]

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("tesseract", 10)

    monkeypatch.setattr("backend.modules.settlement.service.bill_ocr_refine.subprocess.run", timeout)
    assert refine_bl(Image.new("L", (1000, 1200)), readings, "tesseract") is readings
    # 只有订舱号、没有提单号标签时不进行局部复识。
    booking = words([(100, 100, "Booking No. OTHER98765432")])
    assert refine_bl(Image.new("L", (1000, 1200)), [booking, booking], "tesseract") == [booking, booking]
