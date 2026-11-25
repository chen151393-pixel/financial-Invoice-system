"""提单识别模型：适配器请求与容错、返回值校验、与本地规则合并、上传流程、配置校验。

全部使用假的模型响应，不调用任何外部接口。
"""

import base64
import io
import json
from datetime import date

import httpx
import pytest
from backend.core.config import load_settings
from backend.integrations.model_extraction import OpenAICompatibleExtractor, create_extractor
from backend.modules.settlement.policy.bill_model_policy import INSTRUCTIONS, clean, merge
from backend.modules.settlement.service.bill_model_reader import BillModelReader
from backend.tests.settlement.documents_support import Documents, bill_pdf, scanned_bill_pdf
from backend.tests.settlement.test_settlement_batches import create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_bill_ocr import EXPECTED, FakeOcr, words
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from PIL import Image

ANSWER = {
    "bl_no": "TSTUSHATEST58231",
    "port_of_loading": "Ningbo, China",
    "port_of_discharge": "SANTOS, BRAZIL",
    "on_board_date": "2026-11-12",
}


def extractor(handler):
    return OpenAICompatibleExtractor(
        "https://model.example/v1/", "test-key", "test-model", transport=httpx.MockTransport(handler)
    )


def reply(answer):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})


def test_extractor_sends_text_or_image_and_returns_the_json_object():
    seen = []

    def handler(request):
        seen.append(request)
        return reply(ANSWER)

    client = extractor(handler)
    assert client.extract("RULES", text="B/L NO: X") == ANSWER
    assert client.extract("RULES", image_jpeg=b"jpeg-bytes") == ANSWER
    # 没有可发送的内容时不发请求
    assert client.extract("RULES") is None and len(seen) == 2

    first, second = (json.loads(request.content) for request in seen)
    assert str(seen[0].url) == "https://model.example/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert first["model"] == "test-model" and first["response_format"] == {"type": "json_object"}
    assert first["messages"][0] == {"role": "system", "content": "RULES"}
    assert first["messages"][1] == {"role": "user", "content": "B/L NO: X"}
    image = second["messages"][1]["content"][1]
    assert image["type"] == "image_url"
    assert image["image_url"]["url"] == "data:image/jpeg;base64," + base64.b64encode(b"jpeg-bytes").decode()


def timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        timeout,
        lambda request: httpx.Response(401, json={"error": "bad key"}),
        lambda request: httpx.Response(200, text="not json"),
        lambda request: httpx.Response(200, json={"choices": []}),
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "sorry"}}]}),
        lambda request: reply(["not", "an", "object"]),
    ],
)
def test_extractor_failures_return_none(handler):
    assert extractor(handler).extract("RULES", text="anything") is None


def test_factory_only_builds_a_client_when_a_model_is_configured():
    options = {"base_url": "https://model.example", "api_key": "k", "model": "m"}
    assert create_extractor("rules", **options) is None
    assert isinstance(create_extractor("openai_compatible", **options), OpenAICompatibleExtractor)


def test_model_answer_is_validated_field_by_field():
    assert clean(ANSWER) == EXPECTED
    assert clean({"bl_no": "tstu shatest 58231"})["bl_no"] == "TSTUSHATEST58231"
    doubtful = clean(
        {
            "bl_no": "NOT FOUND",  # 没有数字，不是提单号
            "port_of_loading": "PORT OF LOADING",  # 把栏位标签当成了值
            "port_of_discharge": "SANT0S, BRAZIL",  # 口岸含数字
            "on_board_date": "12 NOV 2026",  # 不是约定的日期格式
        }
    )
    assert doubtful == {"bl_no": "", "port_of_loading": "", "port_of_discharge": "", "on_board_date": None}
    assert clean({"on_board_date": "2026-02-30"})["on_board_date"] is None
    assert clean({"bl_no": 12345678, "port_of_loading": None}) == doubtful
    assert clean("not an object") == doubtful


def test_merge_fills_blanks_and_leaves_conflicts_blank():
    ruled = dict(EXPECTED, port_of_discharge="", on_board_date=None)
    merged, taken, conflicts = merge(ruled, EXPECTED)
    assert merged == EXPECTED and taken == ["port_of_discharge", "on_board_date"] and conflicts == []
    # 只差空格和标点不算不一致，保留本地规则的写法
    spaced = dict(EXPECTED, port_of_loading="NINGBO,CHINA")
    assert merge(spaced, EXPECTED) == (spaced, [], [])
    # 两边都有值但不同：留空，不采用任何一方
    other = dict(EXPECTED, bl_no="TSTUSHATEST58237", on_board_date=date(2026, 11, 14))
    merged, taken, conflicts = merge(EXPECTED, other)
    assert merged == dict(EXPECTED, bl_no="", on_board_date=None)
    assert taken == [] and conflicts == ["bl_no", "on_board_date"]
    # 模型没给出的字段保持本地规则的结果
    blank = {"bl_no": "", "port_of_loading": "", "port_of_discharge": "", "on_board_date": None}
    assert merge(EXPECTED, blank) == (EXPECTED, [], [])


class FakeExtractor:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def extract(self, instructions, *, text=None, image_jpeg=None):
        self.calls.append({"instructions": instructions, "text": text, "image_jpeg": image_jpeg})
        return self.answer


def test_reader_sends_text_layer_or_the_scanned_page():
    fake = FakeExtractor(ANSWER)
    reader = BillModelReader(fake)
    assert reader.read(bill_pdf(), "B/L NO: EGLV142503975412") == EXPECTED
    assert fake.calls[0] == {
        "instructions": INSTRUCTIONS,
        "text": "B/L NO: EGLV142503975412",
        "image_jpeg": None,
    }
    assert reader.read(scanned_bill_pdf(), "") == EXPECTED
    sent = Image.open(io.BytesIO(fake.calls[1]["image_jpeg"]))
    # 发彩色原图（不做去底纹的二值化），长边缩到上限以内
    assert sent.format == "JPEG" and sent.mode == "RGB" and max(sent.size) <= 2200
    assert fake.calls[1]["text"] is None
    # 既没有文字层也没有整页图像：不调用模型
    assert reader.read(b"%PDF-broken", "") is None and len(fake.calls) == 2
    # 模型没有返回可用结果
    assert BillModelReader(FakeExtractor(None)).read(bill_pdf(), "text") is None


def test_upload_asks_the_model_only_for_what_rules_left_blank(seeded, tmp_path):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "985.50", fee="15.00")
    garbled = words(replace={"SANTOS, BRAZIL": "SANT0S, BRAZIL"})
    documents = Documents(seeded, tmp_path, FakeOcr([words(), garbled]))
    fake = FakeExtractor(ANSWER)
    documents.bills.model = BillModelReader(fake)

    # 本地规则留空的目的口岸由模型补上；两种来源的字段都提示人工核对
    bill = documents.upload(batch.id, content=scanned_bill_pdf()).bills[0]
    assert bill.portOfDischarge == "SANTOS, BRAZIL" and bill.missing == []
    assert "扫描件由系统识别" in bill.parseNote and "识别模型" in bill.parseNote
    assert len(fake.calls) == 1

    # 本地规则已识别齐全的提单不调用模型
    text_bill = documents.upload(batch.id).bills[1]
    assert text_bill.blNo == "EGLV142503975412" and text_bill.parseNote == ""
    assert len(fake.calls) == 1


def test_upload_blanks_conflicts_and_survives_model_failure(seeded, tmp_path):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "985.50", fee="15.00")
    garbled = words(replace={"SANTOS, BRAZIL": "SANT0S, BRAZIL"})
    documents = Documents(seeded, tmp_path, FakeOcr([words(), garbled]))

    # 模型的提单号与本地规则不一致：提单号留空，模型补上的目的口岸仍采用
    documents.bills.model = BillModelReader(FakeExtractor(dict(ANSWER, bl_no="TSTUSHATEST58237")))
    bill = documents.upload(batch.id, content=scanned_bill_pdf()).bills[0]
    assert bill.blNo == "" and bill.missing == ["提单号"]
    assert bill.portOfDischarge == "SANTOS, BRAZIL"
    assert "提单号" in bill.parseNote and "不一致" in bill.parseNote

    # 模型不可用：结果与只用本地规则时相同
    documents.bills.model = BillModelReader(FakeExtractor(None))
    fallback = documents.upload(batch.id, content=scanned_bill_pdf(((100, 100, "X"),))).bills[1]
    assert fallback.blNo == EXPECTED["bl_no"] and fallback.missing == ["目的口岸"]
    assert "识别模型" not in fallback.parseNote and "对照原件核对" in fallback.parseNote


def test_recognizer_settings_default_to_rules_and_require_a_complete_model_config():
    assert load_settings({}).settlement_bill_recognizer == "rules"
    model = {
        "SETTLEMENT_BILL_RECOGNIZER": "openai_compatible",
        "SETTLEMENT_BILL_MODEL_BASE_URL": "https://api.model.example/v1/",
        "SETTLEMENT_BILL_MODEL_API_KEY": "test-key",
        "SETTLEMENT_BILL_MODEL_NAME": "test-model",
    }
    settings = load_settings(model)
    assert settings.settlement_bill_recognizer == "openai_compatible"
    assert settings.settlement_bill_model_base_url == "https://api.model.example/v1"
    assert settings.settlement_bill_model_timeout == 30
    assert "test-key" not in repr(settings)
    # 本机部署的模型服务可用 HTTP
    assert load_settings({**model, "SETTLEMENT_BILL_MODEL_BASE_URL": "http://localhost:8000/v1"})
    for broken in (
        {"SETTLEMENT_BILL_RECOGNIZER": "anthropic"},
        {**model, "SETTLEMENT_BILL_MODEL_API_KEY": ""},
        {**model, "SETTLEMENT_BILL_MODEL_NAME": ""},
        {**model, "SETTLEMENT_BILL_MODEL_BASE_URL": "http://api.model.example/v1"},
        {**model, "SETTLEMENT_BILL_MODEL_TIMEOUT": "0"},
    ):
        with pytest.raises(ValueError, match="SETTLEMENT_BILL_"):
            load_settings(broken)
