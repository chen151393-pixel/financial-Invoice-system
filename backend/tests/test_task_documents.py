"""NS 合同适配器：账户身份、解析与文件校验。"""

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from backend.core.errors import ApiError
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
