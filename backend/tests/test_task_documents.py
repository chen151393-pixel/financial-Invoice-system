"""原件下载的环境隔离、身份校验、状态推进和来源变化保护。"""

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.integrations.contract_archive import ContractArchive
from backend.integrations.netsuite.subpo_contract import read_contract
from backend.modules.business.entity import load_tables
from backend.modules.reconciliation.dto import TaskListQuery
from backend.modules.reconciliation.task_entity import documents
from backend.modules.reconciliation.task_service import InvoiceTaskService
from backend.tests.test_api import login
from backend.tests.test_finance_list import OWNER
from backend.tests.test_invoice_tasks import approve
from backend.tests.test_invoice_tasks import local_source as local_source
from fastapi.testclient import TestClient
from sqlalchemy import func, select

PDF = b"%PDF-1.4\nexample\n%%EOF"


class ContractSource:
    environment = "production"

    def __init__(self, callback=None):
        self.calls = 0
        self.callback = callback

    def unavailable_reason(self):
        return ""

    def download(self, number, supplier, declaration):
        self.calls += 1
        if self.callback:
            self.callback()
        return {
            "environment": self.environment,
            "ns_id": "548",
            "filename": "subpo-contract-548.pdf",
            "content": PDF,
        }


def task_service(context, source, contract):
    approve(context, source)
    service = InvoiceTaskService(
        context.engine,
        source,
        contract,
        ContractArchive(Path(context.settings.database_url.removeprefix("sqlite:///")).parent),
    )
    task = service.browse(TaskListQuery(), OWNER).groups[0].tasks[0]
    order = service.detail(task.id, OWNER).documents[0].orderId
    return service, task, order


def test_download_persists_and_advances_idempotently(context, local_source):
    contract = ContractSource()
    service, task, order = task_service(context, local_source, contract)
    assert service.detail(task.id, OWNER).prepare.allowed
    detail = service.prepare_document(task.id, order, OWNER)
    assert detail.task.status == "notify_pending"
    assert detail.steps[1].state == "done" and detail.steps[2].state == "current"
    assert detail.documents[0].environment == "production"
    assert detail.documents[0].sha256 and not detail.notify.allowed
    assert Path(detail.documents[0].archivePath).read_bytes() == PDF
    service.prepare_document(task.id, order, OWNER)
    assert contract.calls == 1
    with pytest.raises(ApiError) as error:
        service.prepare_document(task.id, order, "user:someone-else")
    assert error.value.status == 404
    with pytest.raises(ApiError):
        service.prepare_document(task.id, "unrelated-order", OWNER)
    assert contract.calls == 1


def test_source_change_during_download_does_not_store_or_advance(context, local_source):
    def change():
        with local_source.engine.begin() as connection:
            lines = load_tables(connection)["purchase_order_lines"]
            connection.execute(lines.update().where(lines.c.id == 1).values(quantity="101"))

    service, task, order = task_service(context, local_source, ContractSource(change))
    with pytest.raises(ApiError) as error:
        service.prepare_document(task.id, order, OWNER)
    assert error.value.status == 409
    assert service.detail(task.id, OWNER).task.status == "documents_pending"
    with context.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(documents)).scalar_one() == 0


def test_network_failure_keeps_documents_pending(context, local_source):
    def fail():
        raise ApiError(502, "下载超时")

    service, task, order = task_service(context, local_source, ContractSource(fail))
    with pytest.raises(ApiError):
        service.prepare_document(task.id, order, OWNER)
    assert service.detail(task.id, OWNER).documents[0].status == "pending"
    assert service.detail(task.id, OWNER).task.status == "documents_pending"


def test_download_http_auth_prepare_and_attachment(context, local_source, monkeypatch):
    contract = ContractSource()
    service, task, order = task_service(context, local_source, contract)
    monkeypatch.setattr("backend.app.SubpoContractSource", lambda ns: contract)
    context.settings.subpo_archive_root = service.archive.root
    app = create_app(context.settings, context.ns, context.engine, local_source.engine)
    path = f"/api/reconciliation/invoice-tasks/{task.id}/documents/{order}"
    with TestClient(app) as client:
        assert (
            client.post(path + "/prepare", json={}, headers={"Origin": context.settings.origin}).status_code
            == 401
        )
        login(client, context)
        response = client.post(path + "/prepare", json={}, headers={"Origin": context.settings.origin})
        assert response.status_code == 200, response.text
        assert response.json()["task"]["status"] == "notify_pending"
        assert Path(response.json()["documents"][0]["archivePath"]).read_bytes() == PDF
        assert client.get(path + "/file").status_code == 404


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
