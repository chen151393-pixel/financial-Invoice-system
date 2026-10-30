"""专业版分页接入现有同步事件与隔离数据库，验证原子保存和来源隔离。"""

import pytest
from backend.core.errors import ApiError
from backend.integrations.lemon import professional_invoices as protocol
from backend.modules.invoice.entity import headers, items, raw_records, versions
from backend.modules.sync.dto.lemon_invoice_dto import PullLemonInvoices
from backend.tests.sync.test_lemon_invoices import BASE, OWNER, body, count
from backend.tests.sync.test_lemon_invoices import setup as setup
from backend.tests.sync.test_lemon_professional_protocol import SUMMARY, pro_invoice, reader, response
from sqlalchemy import select


def attach(world, pages, calls=None, asid="21"):
    client = reader(pages, calls, [{"asid": int(asid), "asname": "专业账套", "appAsId": "private-context"}])
    world.upstream.professional_accounts = client.accounts.query
    world.upstream.professional_invoices = client.query
    assert world.client.post(BASE + "/account", json={"asid": asid}).status_code == 200


def pull(world, **changes):
    return world.client.post(BASE + "/invoices/pull-save", json=body(asid="21", **changes))


def test_save_repeat_version_and_scope_exclusion(setup):
    first = pro_invoice()
    pages = [response([first, pro_invoice(2, businessTypeText="办公费"), SUMMARY], 2), response([SUMMARY], 2)]
    calls = []
    attach(setup, pages, calls)
    request = body(asid="21")
    initial = setup.client.post(BASE + "/invoices/pull-save", json=request)
    assert initial.status_code == 200
    result = initial.json()["result"]
    assert result["fetched"] == 2 and result["created"] == result["excluded"] == 1
    assert result["pendingDetails"] == 1 and count(setup.engine, items) == 0
    assert setup.client.post(BASE + "/invoices/pull-save", json=request).json() == initial.json()
    assert len(calls) == 2
    assert pull(setup).json()["result"]["unchanged"] == 1
    assert count(setup.engine, versions) == 1
    with setup.engine.connect() as connection:
        header = connection.execute(select(headers)).mappings().one()
        assert header["source"] == "lemon_professional"
        assert header["lemon_account"].startswith("professional:")
        assert connection.scalar(select(raw_records.c.source)) == "lemon_professional"
    detail = setup.client.get(f"/api/invoices/{header['id']}").json()
    assert "private" not in str(detail) and detail["lines"] == []
    first["isInvalid"] = 1
    assert pull(setup).json()["result"]["updated"] == 1
    assert count(setup.engine, versions) == 2
    first["businessTypeText"] = "办公费"
    assert pull(setup).json()["result"]["updated"] == 1
    with setup.engine.connect() as connection:
        assert connection.scalar(select(headers.c.status)) == "unknown"
    first["number"] = "00000000000000000003"
    assert pull(setup).status_code == 409
    assert count(setup.engine, headers) == 1 and count(setup.engine, versions) == 3
    assert setup.upstream.pulls == 0


@pytest.mark.parametrize(
    "second",
    [
        {"state": 401, "data": {}},
        response([pro_invoice(1)], 2),
        response([pro_invoice(2, tax="999")], 2),
        response([pro_invoice(2, invoiceDateText="2026-09-01")], 2),
        response([pro_invoice(2, invoiceCategory=10070)], 2),
        response([pro_invoice(2, number=123)], 2),
    ],
)
def test_late_page_or_business_validation_failure_saves_nothing(setup, monkeypatch, second):
    monkeypatch.setattr(protocol, "PAGE_SIZE", 1)
    attach(setup, [response([pro_invoice(1)], 2), second, response([], 2)])
    result = pull(setup)
    assert result.status_code in (422, 502)
    assert count(setup.engine, headers) == count(setup.engine, versions) == 0
    state = setup.client.get(BASE + "/invoices/configuration").json()
    assert state["latest"]["status"] == "failed" and state["sync"]["allowed"]
    assert setup.upstream.pulls == 0


def test_same_numeric_account_and_invoice_have_separate_edition_namespaces(setup):
    assert setup.client.post(BASE + "/invoices/pull-save", json=body()).status_code == 200
    # 同一编号后来只以专业版出现（两版同时出现同号会被拒绝，见账套服务测试）
    setup.upstream.allowed = []
    attach(setup, [response([pro_invoice(number="26000000000000000001")], 1), response([], 1)], asid="7")
    assert setup.client.post(BASE + "/invoices/pull-save", json=body()).status_code == 200
    with setup.engine.connect() as connection:
        rows = connection.execute(select(headers.c.source, headers.c.lemon_account)).mappings().all()
    assert {row["source"] for row in rows} == {"lemon_open2", "lemon_professional"}
    assert len({row["lemon_account"] for row in rows}) == 2


@pytest.mark.parametrize("api_first", [True, False])
@pytest.mark.parametrize("professional", [True, False])
def test_cross_channel_same_invoice_rejected_in_both_directions(setup, api_first, professional):
    # 与正式 Excel 入口相同的解析、预览和确认流程。

    from backend.modules.invoice.dto.import_dto import ImportBody
    from backend.modules.invoice.service.import_service import ImportService
    from backend.tests.invoice_files import invoice as excel_invoice
    from backend.tests.invoice_files import workbook

    if professional:
        allowed = setup.upstream.allowed
        setup.upstream.professional_accounts = lambda token: [
            {**row, "edition": "professional"} for row in allowed
        ]
        setup.upstream.allowed = []  # 同一账套只属于一个版本
        setup.upstream.professional_invoices = setup.upstream.invoices
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
