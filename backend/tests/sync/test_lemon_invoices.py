"""手动拉票：真实 API、隔离数据库与假上游。"""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.app import create_app, create_events
from backend.core.errors import ApiError
from backend.modules.invoice.entity import headers, items, versions
from backend.modules.invoice.public import InvoicesImported
from backend.modules.sync.dao import lemon_binding_dao as bindings
from backend.modules.sync.dto.lemon_invoice_dto import PullLemonInvoices
from backend.modules.sync.service.lemon_account_service import LemonAccountService
from backend.modules.sync.service.lemon_binding_service import LemonBindingService
from backend.modules.sync.service.lemon_invoice_service import LemonInvoiceService
from backend.tests.test_lemon_binding import FakeLemon, login
from fastapi.testclient import TestClient
from sqlalchemy import func, select

BASE = "/api/sync/lemon"
OWNER = "user:admin"


def invoice(**changes):
    return {
        "InvoiceId": 1,
        "InvoiceCategory": 10080,
        "Number": "26000000000000000001",
        "Code": "",
        "InvoiceDateText": "2026-10-10",
        "Amount": "100.00",
        "Tax": "13.00",
        "AdValoremTaxTotals": "113.00",
        "IsInvalid": 0,
        "Name": "测试供应商",
        "BusinessTypeText": "采购固定资产",
        "InvoiceTypeText": "数电专票",
        **changes,
    }


class FakeInvoices:
    def __init__(self):
        self.rows = [invoice()]
        self.allowed = [{"asid": "7", "name": "测试账套"}, {"asid": "8", "name": "另一账套"}]
        self.pulls = 0
        self.failure = None

    def user_token(self, mobile):
        assert mobile == "13800000001"
        return "private-user-token"

    def accounts(self, token):
        return deepcopy(self.allowed)

    def account_service_ids(self, token, asid=None):
        return []

    def invoices(self, token, asid, start, end):
        self.pulls += 1
        if self.failure:
            raise self.failure
        return deepcopy(self.rows)


def make_services(engine, settings):
    binding = LemonBindingService(settings, engine, FakeLemon())
    with engine.begin() as connection:
        bindings.prepare(connection, binding._scope(OWNER), OWNER, "13800000001")
        bindings.transition(connection, binding._scope(OWNER), ("unbound",), "bound")
    upstream = FakeInvoices()
    accounts = LemonAccountService(binding, upstream)
    accounts.select(OWNER, "7")
    events = create_events()
    return accounts, LemonInvoiceService(accounts, events), upstream, events


def body(**changes):
    return {
        "requestId": str(uuid4()),
        "asid": "7",
        "startDate": "2026-10-01",
        "endDate": "2026-10-16",
        **changes,
    }


@pytest.fixture
def setup(context):
    settings = replace(
        context.settings,
        origin="https://invoice.example",
        lemon_app_id="12345",
        lemon_app_secret="secret",
        lemon_redirect_uri="https://invoice.example/api/lemon/oauth/callback",
    )
    accounts, service, upstream, events = make_services(context.engine, settings)
    app = create_app(
        settings, context.ns, context.engine, lemon=accounts.binding.client, lemon_invoices=upstream
    )
    with TestClient(app, base_url=settings.origin) as client:
        client.headers["Origin"] = settings.origin
        login(client, settings)
        yield SimpleNamespace(
            client=client,
            service=service,
            accounts=accounts,
            upstream=upstream,
            events=events,
            engine=context.engine,
        )


def count(engine, table):
    with engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(table))


def test_save_duplicate_version_and_persistent_result(setup):
    world = setup
    request = body()
    response = world.client.post(BASE + "/invoices/pull-save", json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed" and result["result"]["created"] == 1
    assert result["result"]["pendingDetails"] == 1 and count(world.engine, items) == 0
    with world.engine.connect() as connection:
        header = connection.execute(select(headers)).mappings().one()
        assert header["detail_status"] == "pending" and header["currency"] == "CNY"
        assert str(header["amount_including_tax"]) == "113.00"
    assert world.client.post(BASE + "/invoices/pull-save", json=request).json() == result
    assert world.upstream.pulls == 1
    detail = world.client.get(f"/api/invoices/{header['id']}").json()
    assert "待补齐" in detail["detailStatusLabel"] and detail["lines"] == []
    assert world.client.get(BASE + "/runs/" + request["requestId"]).json() == result
    assert world.client.post(BASE + "/invoices/pull-save", json=body()).json()["result"]["unchanged"] == 1
    assert count(world.engine, versions) == 1
    world.upstream.rows[0]["IsInvalid"] = 1
    assert world.client.post(BASE + "/invoices/pull-save", json=body()).json()["result"]["updated"] == 1
    assert count(world.engine, versions) == 2
    with world.engine.connect() as connection:
        assert connection.scalar(select(headers.c.status)) == "void"


@pytest.mark.parametrize(
    "changes",
    [
        {"Amount": "100.001"},
        {"Tax": "14"},
        {"InvoiceDateText": "2026-09-01"},
        {"InvoiceCategory": 10070},
        {"Number": 26000000000000000001},
        {"BusinessTypeText": ""},
        {"Amount": "NaN"},
    ],
)
def test_invalid_batch_rolls_back_all_rows(setup, changes):
    setup.upstream.rows.append(
        invoice(
            InvoiceId=2, Number="26000000000000000002", **{k: v for k, v in changes.items() if k != "Number"}
        )
    )
    if "Number" in changes:
        setup.upstream.rows[-1]["Number"] = changes["Number"]
    response = setup.client.post(BASE + "/invoices/pull-save", json=body())
    assert response.status_code == 422, response.text
    assert count(setup.engine, headers) == count(setup.engine, versions) == 0
    state = setup.client.get(BASE + "/invoices/configuration").json()
    assert state["latest"]["status"] == "failed" and state["sync"]["allowed"]


def test_unauthorized_account_date_and_service_identity_rejected(setup, context):
    assert setup.client.post(BASE + "/account", json={"asid": "999"}).status_code == 403
    assert setup.client.post(BASE + "/invoices/pull-save", json=body(asid="8")).status_code == 409
    for changes in (
        {"startDate": ""},
        {"endDate": "2026-09-01"},
        {"startDate": "2020-01-01"},
        {"owner": "other"},
    ):
        assert setup.client.post(BASE + "/invoices/pull-save", json=body(**changes)).status_code == 400
    assert setup.upstream.pulls == 0
    setup.client.cookies.clear()
    assert setup.client.get(BASE + "/invoices/configuration").status_code == 401
    assert (
        setup.client.post(
            BASE + "/invoices/pull-save",
            json=body(),
            headers={"Authorization": "Bearer " + context.settings.service_key},
        ).status_code
        == 403
    )


def test_account_permission_rechecked_and_namespaces_isolated(setup):
    setup.service.pull(OWNER, PullLemonInvoices(**body()))
    setup.accounts.select(OWNER, "8")
    setup.service.pull(OWNER, PullLemonInvoices(**body(asid="8")))
    assert count(setup.engine, headers) == 2
    setup.upstream.allowed = []
    with pytest.raises(ApiError, match="访问权限"):
        setup.service.pull(OWNER, PullLemonInvoices(**body(asid="8")))
    assert count(setup.engine, headers) == 2


def test_request_payload_conflict_and_restart_do_not_reexecute(setup):
    request = PullLemonInvoices(**body())
    setup.service._start(OWNER, request)
    restarted = LemonInvoiceService(setup.accounts, setup.events)
    assert restarted.pull(OWNER, request)["status"] == "running"
    assert setup.upstream.pulls == 0
    assert not setup.accounts.configuration(OWNER)["sync"]["allowed"]
    with pytest.raises(ApiError, match="待核实"):
        restarted.pull(OWNER, PullLemonInvoices(**body()))
    with pytest.raises(ApiError, match="不同账套或日期"):
        restarted.pull(OWNER, PullLemonInvoices(**{**request.model_dump(), "endDate": "2026-10-15"}))


def test_subscriber_failure_rolls_back_invoice_and_result(setup):
    def fail(connection, event):
        raise ApiError(409, "测试订阅失败")

    setup.events.subscribe(InvoicesImported, fail)
    with pytest.raises(ApiError, match="订阅失败"):
        setup.service.pull(OWNER, PullLemonInvoices(**body()))
    assert count(setup.engine, headers) == count(setup.engine, versions) == 0
    assert setup.accounts.configuration(OWNER)["latest"]["status"] == "failed"


def test_empty_excluded_unknown_and_stable_source_identity(setup):
    setup.upstream.rows = []
    assert setup.service.pull(OWNER, PullLemonInvoices(**body()))["result"]["fetched"] == 0
    setup.upstream.rows = [invoice(BusinessTypeText="购买服务")]
    assert setup.service.pull(OWNER, PullLemonInvoices(**body()))["result"]["excluded"] == 1
    assert count(setup.engine, headers) == 0
    setup.upstream.rows = [invoice(IsInvalid=999)]
    setup.service.pull(OWNER, PullLemonInvoices(**body()))
    with setup.engine.connect() as connection:
        assert connection.scalar(select(headers.c.status)) == "unknown"
    setup.upstream.rows[0]["Number"] = "26000000000000000002"
    with pytest.raises(ApiError, match="票号发生变化"):
        setup.service.pull(OWNER, PullLemonInvoices(**body()))
    assert count(setup.engine, headers) == 1


def test_changed_business_type_invalidates_previously_imported_header(setup):
    setup.service.pull(OWNER, PullLemonInvoices(**body()))
    setup.upstream.rows[0]["BusinessTypeText"] = "购买服务"
    result = setup.service.pull(OWNER, PullLemonInvoices(**body()))
    assert result["result"]["updated"] == 1
    with setup.engine.connect() as connection:
        row = connection.execute(select(headers)).mappings().one()
        assert row["status"] == "unknown" and row["business_type"] == "购买服务"


@pytest.mark.parametrize("api_first", [True, False])
def test_cross_channel_same_invoice_rejected_in_both_directions(setup, api_first):
    # 与正式 Excel 入口相同的解析、预览和确认流程。

    from backend.modules.invoice.dto.import_dto import ImportBody
    from backend.modules.invoice.service.import_service import ImportService
    from backend.tests.invoice_files import invoice as excel_invoice
    from backend.tests.invoice_files import workbook

    number = "26000000000000000001"
    content = workbook([excel_invoice(number, [("墨水", "个", "1", "100", "13")])])
    importer = ImportService(setup.engine, setup.events)
    request = ImportBody(filename="test.xlsx", content=content)
    if api_first:
        setup.service.pull(OWNER, PullLemonInvoices(**body()))
        preview = importer.process(request, OWNER)
        assert preview.conflicts == 1 and not preview.allowed
    else:
        preview = importer.process(request, OWNER)
        importer.process(
            request.model_copy(update={"previewToken": preview.previewToken}), OWNER, commit=True
        )
        with pytest.raises(ApiError, match="Excel"):
            setup.service.pull(OWNER, PullLemonInvoices(**body()))
    assert count(setup.engine, headers) == 1


def test_account_query_uses_authenticated_json_request(setup):
    response = setup.client.post(BASE + "/accounts/query", json={})
    assert response.status_code == 200 and len(response.json()["items"]) == 2
    assert "private" not in response.text


def test_invalid_date_range_returns_safe_specific_reason(setup):
    response = setup.client.post(BASE + "/invoices/pull-save", json=body(endDate="2026-09-01"))
    assert response.status_code == 400
    assert "起止日期须按先后顺序填写" in response.json()["error"]
    assert setup.upstream.pulls == 0
