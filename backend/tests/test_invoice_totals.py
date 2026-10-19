"""发票顶部统计：真实导入、匹配确认与复核链路；查询无写入，统计覆盖筛选全量。"""

from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.modules.invoice.dto.invoice_dto import InvoiceQuery
from backend.modules.invoice.entity import headers
from backend.modules.invoice.service.invoice_service import InvoiceService
from backend.modules.matching.dto.invoice_totals_dto import InvoiceTotalsQuery
from backend.modules.matching.dto.matching_dto import CancelBody, ConfirmBody
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_task import USER
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

NUMBER = "26000000000000009501"


def totals(world, **filters):
    return world["queries"].invoice_totals(InvoiceTotalsQuery(**filters)).amounts


def amount(row, name):
    return Decimal(getattr(row, name))


def prepare(engine, world):
    import_invoices(world, [invoice(NUMBER, [INK, FLUID], remark="SUB-200")])
    return proposals(world, invoice_id(engine, NUMBER))


def test_empty_and_proposals_do_not_reduce_pending(engine, world, reviewed):
    assert totals(world) == []
    prepare(engine, world)
    result = totals(world)[0]
    assert (result.currency, result.count, result.pendingCount, result.reviewCount) == ("CNY", 1, 1, 0)
    assert amount(result, "gross") == amount(result, "pendingAmount") == Decimal("120.50")
    assert amount(result, "tax") == Decimal("13.86") and amount(result, "reviewAmount") == 0


def test_confirm_partial_complete_cancel(engine, world, reviewed):
    first, second = prepare(engine, world)
    world["allocations"].confirm(int(first.id), ConfirmBody(), USER)
    assert amount(totals(world)[0], "pendingAmount") == Decimal("20")
    world["allocations"].confirm(int(second.id), ConfirmBody(), USER)
    assert amount(totals(world)[0], "pendingAmount") == 0 and totals(world)[0].pendingCount == 0
    world["allocations"].cancel(int(first.id), CancelBody(reason="统计撤销回归"), USER)
    assert amount(totals(world)[0], "pendingAmount") == Decimal("100.50")


def test_version_review_history_and_cancellation(engine, world, reviewed):
    first, _ = prepare(engine, world)
    world["allocations"].confirm(int(first.id), ConfirmBody(), USER)
    import_invoices(world, [invoice(NUMBER, [INK, FLUID], remark="SUB-200 补充说明")])
    result = totals(world)[0]
    assert amount(result, "pendingAmount") == Decimal("120.50")
    assert amount(result, "reviewAmount") == Decimal("100.50") and result.reviewCount == 1
    world["allocations"].reverify(int(first.id), ConfirmBody(note="核实新版本"), USER)
    assert amount(totals(world)[0], "pendingAmount") == Decimal("20")
    assert amount(totals(world)[0], "reviewAmount") == 0


@pytest.mark.parametrize("status", ["作废", "已红冲", "未知状态"])
def test_invalid_invoice_excluded_from_pending_keeps_review(engine, world, reviewed, status):
    found = prepare(engine, world)
    for row in found:
        world["allocations"].confirm(int(row.id), ConfirmBody(), USER)
    import_invoices(world, [invoice(NUMBER, [INK, FLUID], remark="SUB-200", status=status)])
    result = totals(world)[0]
    assert amount(result, "pendingAmount") == 0
    assert amount(result, "reviewAmount") == Decimal("120.50") and result.reviewCount == 1
    world["allocations"].cancel(int(found[0].id), CancelBody(reason="撤销失效占用"), USER)
    assert amount(totals(world)[0], "reviewAmount") == Decimal("20")


def test_filters_multiple_currencies_and_negative_invoice(engine, world):
    import_invoices(
        world,
        [
            invoice(NUMBER, [INK]),
            invoice("26000000000000009502", [FLUID], seller="第二供应商"),
            invoice("26000000000000009503", [("退货", "个", "-1", "-10.00", "-1.30")], status="已红冲"),
        ],
    )
    with engine.begin() as connection:
        connection.execute(
            update(headers).where(headers.c.invoice_no == "26000000000000009502").values(currency="USD")
        )
    groups = {row.currency: row for row in totals(world)}
    assert amount(groups["CNY"], "gross") == Decimal("89.20")
    assert amount(groups["CNY"], "tax") == Decimal("10.26")
    assert amount(groups["CNY"], "pendingAmount") == Decimal("100.50")
    assert amount(groups["USD"], "pendingAmount") == Decimal("20")
    assert totals(world, q="第二")[0].currency == "USD"
    assert totals(world, status="red_letter")[0].count == 1
    assert totals(world, status="red_offset") == []
    assert totals(world, date_from="2026-10-11") == []
    assert totals(world, date_from="2026-10-10", date_to="2026-10-10")[0].count == 2
    assert totals(world, q="%") == []


def test_all_pages_and_header_only_invoices(engine, world):
    import_invoices(world, [invoice(NUMBER, [INK])])
    with engine.begin() as connection:
        template = dict(connection.execute(select(headers)).mappings().one())
        template.pop("id")
        copies = [
            {
                **template,
                "invoice_no": f"26000000000001{index:06}",
                "invoice_key": f":26000000000001{index:06}",
                "detail_status": "pending",
            }
            for index in range(502)
        ]
        connection.execute(insert(headers), copies)
    result = totals(world)[0]
    page = InvoiceService(engine).browse(InvoiceQuery(page=2, page_size=10))
    assert len(page.rows) == 10 and result.count == page.total == 503
    assert amount(result, "pendingAmount") == Decimal("100.50") * 503
    assert amount(result, "gross") == Decimal(page.amounts[0].gross)
    assert amount(result, "tax") == Decimal(page.amounts[0].tax)


def test_red_letter_display_and_filter_include_existing_normal_negative_invoices(engine, world):
    states = ["正常", "正常", "已红冲", "已红冲", "作废", "未知状态"]
    import_invoices(
        world,
        [
            invoice(
                f"2600000000000000960{index}",
                [
                    (
                        "商品",
                        "个",
                        "-1" if negative else "1",
                        "-10.00" if negative else "10.00",
                        "-1.30" if negative else "1.30",
                    )
                ],
                status=status,
            )
            for index, (status, negative) in enumerate(
                zip(states, [False, True, False, True, True, True], strict=True)
            )
        ],
    )
    service = InvoiceService(engine)
    expected = {
        "normal": (1, "正常"),
        "red_letter": (2, "红字发票"),
        "red_offset": (1, "已被红冲"),
        "void": (1, "作废"),
        "unknown": (1, "未知"),
    }
    for status, (count, label) in expected.items():
        result = service.browse(InvoiceQuery(status=status, page_size=1))
        aggregate = totals(world, status=status)[0]
        assert result.total == count == aggregate.count
        assert result.rows[0].displayStatus == status and result.rows[0].status == label
        assert Decimal(result.amounts[0].gross) == amount(aggregate, "gross")
    red = service.browse(InvoiceQuery(status="red_letter", page=2, page_size=1)).rows[0]
    assert red.sourceStatus == "normal" and red.displayStatus == "red_letter"
    assert service.detail(int(red.id)).status == "红字发票"
    assert amount(totals(world, status="red_letter")[0], "gross") == Decimal("-22.60")


def test_http_auth_validation_and_read_only_contract(engine, env):
    app = create_app(load_settings(env), engine=engine)
    with TestClient(app) as client:
        path = "/api/matching/invoice-totals"
        assert client.get(path).status_code == 401
        auth = {"Authorization": "Bearer " + env["SERVICE_API_KEY"]}
        assert client.get(path, headers=auth).json() == {"amounts": []}
        for params in (
            {"date_from": "2026-11-01", "date_to": "2026-10-01"},
            {"status": "bad"},
            {"page": "1"},
        ):
            assert client.get(path, params=params, headers=auth).status_code == 400
