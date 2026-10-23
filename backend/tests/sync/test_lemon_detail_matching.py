"""真实服务链路：专业版协议 → 补全 → 建议 → 人工确认 → 收齐、版本复核和撤销。"""

from copy import deepcopy
from dataclasses import replace

import httpx
import pytest
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.integrations.lemon.professional_invoice_details import LemonProfessionalInvoiceDetails
from backend.integrations.lemon.professional_invoices import LemonProfessionalInvoices
from backend.modules.invoice.entity import headers, items, versions
from backend.modules.invoice.public import InvoicesImported
from backend.modules.matching.dto.matching_dto import CancelBody, ConfirmBody
from backend.modules.sync.dto.lemon_invoice_dto import PullLemonInvoices
from backend.tests.documents_ready import complete_documents
from backend.tests.sync.lemon_detail_fixtures import full_invoice
from backend.tests.sync.test_lemon_account_services import adapter, reply
from backend.tests.sync.test_lemon_invoices import OWNER, body, count, make_services
from backend.tests.sync.test_lemon_professional_protocol import response
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import proposals, task
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import rows
from sqlalchemy import select


def flow_settings(env):
    return replace(
        load_settings(env),
        origin="https://invoice.example",
        lemon_app_id="12345",
        lemon_app_secret="secret",
        lemon_redirect_uri="https://invoice.example/api/lemon/oauth/callback",
    )


@pytest.fixture
def flow(engine, env, world):
    accounts, service, upstream, events = make_services(engine, flow_settings(env))
    raw = full_invoice(
        Amount="106.64",
        Tax="13.86",
        AdValoremTaxTotals="120.50",
        Note="SUB-200",
        Name="上海 供应商（有限）公司",
    )
    raw["Detail"]["invoiceEntries"] = [
        {
            "name": "墨水",
            "model": "A",
            "unit": "个",
            "quality": "10",
            "amount": "88.94",
            "tax": "11.56",
            "taxRate": "13",
        },
        {
            "name": "清洗液",
            "model": "B",
            "unit": "个",
            "quality": "10",
            "amount": "17.70",
            "tax": "2.30",
            "taxRate": "13",
        },
    ]
    state = {"raw": raw, "detail_calls": 0, "fail": False}

    def handler(request):
        if request.url.path == "/api/Invoice/PurchasePagingList":
            head = {
                key[:1].lower() + key[1:]: value for key, value in state["raw"].items() if key != "Detail"
            }
            return httpx.Response(
                200, json=response([head] if request.url.params["pageIndex"] == "1" else [], 1)
            )
        if request.url.path == "/api/Invoice":
            state["detail_calls"] += 1
            if state["fail"]:
                return httpx.Response(503)
            return httpx.Response(200, json={"state": 1000, "data": {"invoiceData": state["raw"]["Detail"]}})
        return reply(request)

    protocol = adapter(handler)
    upstream.professional_accounts = protocol.query
    upstream.professional_invoices = LemonProfessionalInvoices(protocol).query
    upstream.invoice_details = lambda token, asid, records, selected_ids, professional: (
        LemonProfessionalInvoiceDetails(protocol).enrich(token, asid, records, selected_ids)
    )
    accounts.select(OWNER, "21")
    return state, service, events


def pull(flow):
    return flow[1].pull(OWNER, PullLemonInvoices(**body(asid="21")))


def target(engine):
    with engine.connect() as connection:
        return connection.scalar(select(headers.c.id))


def test_professional_read_confirm_complete_cancel_and_repeat(engine, world, reviewed, flow):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    request = PullLemonInvoices(**body(asid="21"))
    first = flow[1].pull(OWNER, request)
    assert first["result"]["completeDetails"] == 1 and first["result"]["pendingDetails"] == 0
    assert flow[1].pull(OWNER, request) == first and flow[0]["detail_calls"] == 1
    found = proposals(world, target(engine))
    assert len(found) == 2
    for candidate in found:
        world["allocations"].confirm(int(candidate.id), ConfirmBody(), OWNER)
    assert task(engine)["status"] == "completed"
    assert pull(flow)["result"]["unchanged"] == 1
    assert count(engine, versions) == 1 and not proposals(world, target(engine))
    world["allocations"].cancel(int(found[0].id), CancelBody(reason="测试撤销"), OWNER)
    assert task(engine)["status"] == "partially_received"


def test_reordering_no_new_version_changed_quantity_reopens_review(engine, world, reviewed, flow):
    pull(flow)
    found = proposals(world, target(engine))
    for candidate in found:
        world["allocations"].confirm(int(candidate.id), ConfirmBody(), OWNER)
    before = rows(engine, "SELECT id, item_name FROM invoice_items ORDER BY id")
    entries = flow[0]["raw"]["Detail"]["invoiceEntries"]
    entries.reverse()
    assert pull(flow)["result"]["unchanged"] == 1
    entries[0]["quality"] = "11"
    assert pull(flow)["result"]["updated"] == 1
    assert rows(engine, "SELECT id, item_name FROM invoice_items ORDER BY id") == before
    allocation_rows = rows(engine, "SELECT status, verification_status FROM matching_allocations")
    assert all(row["status"] == "confirmed" for row in allocation_rows)
    assert any(row["verification_status"] != "valid" for row in allocation_rows)
    assert task(engine)["status"] != "completed"


def test_invoice_first_then_review_and_regenerate(engine, world, ns, flow):
    from backend.tests.test_source_storage import bundle, customs, purchase, save
    from backend.tests.test_task import approve

    pull(flow)
    assert not proposals(world, target(engine))
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")
    assert world["proposals"].generate_now([target(engine)], OWNER) == 2


def test_detail_failure_and_subscriber_failure_preserve_previous_ledger(engine, world, reviewed, flow):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    pull(flow)
    for candidate in proposals(world, target(engine)):
        world["allocations"].confirm(int(candidate.id), ConfirmBody(), OWNER)
    before = deepcopy(rows(engine, "SELECT * FROM matching_allocations"))
    flow[0]["fail"] = True
    with pytest.raises(ApiError, match="HTTP 503"):
        pull(flow)
    flow[0]["fail"] = False
    flow[0]["raw"]["Detail"]["invoiceEntries"][0]["quality"] = "11"

    def fail(connection, event):
        raise ApiError(409, "模拟下游失败")

    flow[2].subscribe(InvoicesImported, fail)
    with pytest.raises(ApiError, match="模拟下游失败"):
        pull(flow)
    assert count(engine, versions) == 1 and count(engine, items) == 2
    assert rows(engine, "SELECT * FROM matching_allocations") == before
    assert task(engine)["status"] == "completed"


@pytest.mark.parametrize("status", [1, 2])
def test_void_or_red_invoice_removes_effective_receipts(engine, world, reviewed, flow, status):
    pull(flow)
    for candidate in proposals(world, target(engine)):
        world["allocations"].confirm(int(candidate.id), ConfirmBody(), OWNER)
    flow[0]["raw"]["IsInvalid"] = status
    flow[0]["raw"]["Detail"]["isInvalid"] = status
    pull(flow)
    assert not proposals(world, target(engine)) and task(engine)["status"] != "completed"
