"""NS 原件适配器：子采购合同与报关资料的账户身份、解析与文件校验。"""

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from backend.core.errors import ApiError
from backend.integrations.netsuite.declaration_documents import read_documents
from backend.integrations.netsuite.subpo_contract import read_contract

PDF = b"%PDF-1.4\nexample\n%%EOF"


def adapter(handler, *, supplier="供应商", declaration="CD000252"):
    settings = SimpleNamespace(
        account="5939865",
        subpo_contract_script="476",
        subpo_contract_deploy="1",
        scope=["restlets", "rest_webservices"],
    )
    ns = SimpleNamespace(
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        token=lambda: "test-token",
    )
    ns.filtered_ids = lambda kind, field, number: ["548"]
    ns.request = lambda *args: {
        "data": {
            "id": "548",
            "name": "SUB-1",
            "custrecord_swc_subpo_vendor": {"refName": supplier},
            "custrecord_swc_subpo_baoguannum": {"refName": declaration},
        }
    }
    return ns


def test_adapter_uses_production_resolved_id_and_double_json():
    def respond(request):
        assert request.method == "GET"
        assert request.url.host == "5939865.restlets.api.netsuite.com"
        assert dict(request.url.params) == {"script": "476", "deploy": "1", "zid": "548"}
        return httpx.Response(
            200,
            json=json.dumps(
                {"zid": 548, "filename": "../../bad.pdf", "contentBase64": base64.b64encode(PDF).decode()}
            ),
        )

    ns = adapter(respond)
    try:
        result = read_contract(ns, "SUB-1", "供应商", "CD000252")
        assert result["filename"] == "subpo-contract-548.pdf" and result["content"] == PDF
    finally:
        ns.client.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"zid": 549, "contentBase64": base64.b64encode(PDF).decode()},
        {"zid": 548, "contentBase64": "not-base64!"},
        {"zid": 548, "contentBase64": base64.b64encode(b"%PDF-truncated").decode()},
        {"zid": 548},
    ],
)
def test_adapter_rejects_wrong_id_and_invalid_pdf(payload):
    ns = adapter(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(ApiError) as error:
            read_contract(ns, "SUB-1", "供应商", "CD000252")
        assert error.value.status == 502
    finally:
        ns.client.close()


def test_adapter_refuses_environment_identity_mismatch_before_pdf_request():
    def no_download(request):
        pytest.fail("identity mismatch must not fetch PDF")

    ns = adapter(no_download, supplier="另一供应商")
    try:
        with pytest.raises(ApiError) as error:
            read_contract(ns, "SUB-1", "供应商", "CD000252")
        assert error.value.status == 409
    finally:
        ns.client.close()


def declaration_adapter(handler, *, real_no="REAL870", script="901"):
    settings = SimpleNamespace(
        account="5939865",
        declaration_doc_script=script,
        declaration_doc_deploy="1" if script else "",
        scope=["restlets", "rest_webservices"],
    )
    ns = SimpleNamespace(
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        token=lambda: "test-token",
    )
    ns.filtered_ids = lambda kind, field, number: ["870"]
    ns.request = lambda *args: {"data": {"id": "870", "name": "CD870", "custrecord_swc_realno": real_no}}
    return ns


def files_payload(files, *, record="870", kind="invoice"):
    return {
        "id": record,
        "type": kind,
        "files": [
            {"filename": "x.pdf", "contentBase64": base64.b64encode(content).decode()} for content in files
        ],
    }


def test_declaration_documents_located_by_cd_number_and_return_all_pdfs():
    def respond(request):
        assert dict(request.url.params) == {"script": "901", "deploy": "1", "id": "870", "type": "invoice"}
        return httpx.Response(200, json=json.dumps(files_payload([PDF, PDF + b" "])))

    ns = declaration_adapter(respond)
    try:
        result = read_documents(ns, "CD870", "REAL870", "invoice")
        assert result["ns_id"] == "870" and result["files"] == [PDF, PDF + b" "]
    finally:
        ns.client.close()


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        (files_payload([]), 404),
        (files_payload([PDF], kind="sales_contract"), 502),
        (files_payload([PDF], record="871"), 502),
        (files_payload([b"%PDF-truncated"]), 502),
    ],
)
def test_declaration_documents_reject_empty_wrong_or_invalid_files(payload, status):
    ns = declaration_adapter(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(ApiError) as error:
            read_documents(ns, "CD870", "REAL870", "invoice")
        assert error.value.status == status
    finally:
        ns.client.close()


def test_declaration_documents_refuse_identity_mismatch_and_missing_configuration():
    def no_download(request):
        pytest.fail("identity mismatch must not fetch files")

    ns = declaration_adapter(no_download, real_no="OTHER")
    try:
        with pytest.raises(ApiError) as error:
            read_documents(ns, "CD870", "REAL870", "invoice")
        assert error.value.status == 409
    finally:
        ns.client.close()
    ns = declaration_adapter(no_download, script="")
    try:
        with pytest.raises(ApiError, match="尚未配置") as error:
            read_documents(ns, "CD870", "REAL870", "invoice")
        assert error.value.status == 503
    finally:
        ns.client.close()
