"""申报幅度与价格校验（2026-10-23）：销售单汇率换算申报价、财务核对申报幅度、比对申报价校验与"只看异常"。

SQLite 隔离库，合成 NS 数据：报关行 15 USD，销售单汇率 7.1，申报价 106.5 元；子采购含税 100.5 / 20 元。
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dto.matching_dto import BatchBody, ConfirmBody, QueueQuery
from backend.modules.review.mapper.declaration_mapper import declaration
from backend.modules.review.policy.margin_policy import declared_margin
from backend.modules.source.policy.declared_price_policy import declared_cny, pick_sales_order
from backend.modules.source.service.sales_order_reader import WARNING, read_sales_orders
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import reviewed as reviewed  # 共用夹具
from backend.tests.test_matching import world as world  # 共用夹具
from backend.tests.test_review import events as events  # 共用夹具
from backend.tests.test_review import group
from backend.tests.test_review import service as service  # 共用夹具
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from backend.tests.test_task import USER
from sqlalchemy import text


def set_rate(engine, rate):
    with engine.begin() as connection:
        value = None if rate is None else str(rate)
        connection.execute(text("UPDATE source_sales_orders SET exchange_rate = :r"), {"r": value})


def test_sales_order_choice_and_cny_conversion():
    usd = {"id": 1, "order_no": "SO1", "currency": "USD", "exchange_rate": Decimal("7.1")}
    other = {"id": 2, "order_no": "SO2", "currency": "USD", "exchange_rate": Decimal("7.2")}
    assert pick_sales_order("SO2", [usd, other, usd]) == (other, "")
    assert pick_sales_order("SO9", [usd, usd]) == (usd, "")
    assert pick_sales_order("SO9", [usd, other]) == (None, "对应销售单不唯一")
    assert declared_cny(Decimal("15"), Decimal("1.5"), "USD", usd)[:2] == (Decimal("106.5"), Decimal("10.65"))
    assert declared_cny(Decimal("15"), None, "CNY", None)[0] == Decimal("15")
    assert declared_cny(Decimal("15"), None, "EUR", usd)[2] == "报关行币种与销售单币种不一致"
    assert declared_cny(Decimal("15"), None, "USD", {**usd, "exchange_rate": None})[2] == "销售单汇率待同步"


@pytest.mark.parametrize("currency", ["USD", "US Dollar", "美元", " us dollar "])
def test_margin_uses_unit_prices_and_skips_unit_mismatch(currency):
    customs_row = {
        "unit": "个",
        "amount": Decimal("15"),
        "unit_price": Decimal("1.5"),
        "currency": currency,
        "sales_order_no": "SO1",
    }
    orders = {1: {"currency": "CNY", "sales_order_id": 9}}
    sales = {9: {"id": 9, "order_no": "SO1", "currency": "USD", "exchange_rate": Decimal("7.1")}}
    line = {
        "unit": "个",
        "unit_price": Decimal("12"),
        "amount": Decimal("60"),
        "quantity": Decimal("5"),
        "purchase_order_id": 1,
    }
    result = declared_margin(customs_row, [line, {**line, "amount": Decimal("40.5")}], orders, sales)
    assert (result["status"], result["margin"], result["declared"]) == (
        "ok",
        Decimal("5.63"),
        Decimal("10.65"),
    )
    assert result["purchase"] == Decimal("10.05")
    negative = declared_margin(customs_row, [line], orders, sales)
    assert negative["status"] == "negative" and negative["margin"] == Decimal("-12.68")
    assert negative["note"] == "报关单价低于采购价"
    weighted = declared_margin(
        customs_row, [line, {**line, "amount": Decimal("20"), "quantity": Decimal("10")}], orders, sales
    )
    assert weighted["purchase"] == Decimal("80") / Decimal("15")
    assert declared_margin({**customs_row, "amount": None}, [line], orders, sales) == (
        declared_margin(customs_row, [line], orders, sales)
    )
    for value in (None, Decimal(0)):
        assert declared_margin({**customs_row, "unit_price": value}, [line], orders, sales)["margin"] is None
    for field, value in (("amount", None), ("quantity", None), ("quantity", Decimal(0))):
        assert declared_margin(customs_row, [{**line, field: value}], orders, sales)["margin"] is None
    mismatch = declared_margin(customs_row, [{**line, "unit": "千克"}], orders, sales)
    assert mismatch["status"] == "unavailable" and "单位不一致" in mismatch["note"]
    missing = declared_margin(customs_row, [line], orders, {})
    assert missing["status"] == "unavailable" and missing["margin"] is None


@pytest.mark.parametrize("currency", ["CNY", "人民币", "Chinese Yuan"])
def test_cny_names_do_not_require_exchange_rate(currency):
    assert declared_cny(Decimal("15"), Decimal("1.5"), currency, None) == (Decimal("15"), Decimal("1.5"), "")


@pytest.mark.parametrize("currency", [None, "", "1", "$", "元", "UNKNOWN"])
def test_unknown_currency_does_not_use_available_rate(currency):
    sales = {"currency": currency, "exchange_rate": Decimal("6.71")}
    assert declared_cny(Decimal("2127.27"), None, currency, sales) == (None, None, "报关行币种待核实")
    assert declared_cny(Decimal("2127.27"), None, "USD", sales) == (None, None, "销售单币种待核实")


def test_customs_currency_name_uses_synced_sales_rate():
    sales = {"currency": "USD", "exchange_rate": Decimal("6.71")}
    assert declared_cny(Decimal("2127.27"), Decimal("35.45"), "US Dollar", sales) == (
        Decimal("14273.9817"),
        Decimal("237.8695"),
        "",
    )
    assert declared_cny(Decimal("2127.27"), None, "Euro", sales)[2] == ("报关行币种与销售单币种不一致")


def test_margin_does_not_display_negative_zero():
    result = declared_margin(
        {
            "unit": "片",
            "amount": Decimal("2127.27"),
            "unit_price": Decimal("35.45"),
            "currency": "US Dollar",
            "sales_order_no": "SO1",
        },
        [{"unit": "片", "amount": Decimal("237.87"), "quantity": Decimal("1"), "purchase_order_id": 1}],
        {1: {"currency": "CNY", "sales_order_id": 9}},
        {9: {"id": 9, "order_no": "SO1", "currency": "USD", "exchange_rate": Decimal("6.71")}},
        tolerance=Decimal("0"),
    )
    assert str(result["margin"]) == "0.00"
    assert result["status"] == "negative"  # 关闭容差时，即使幅度舍入为零仍提示倒挂
    assert result["note"] == "报关单价低于采购价"


def test_review_page_shows_margin_per_customs_line(ns, engine, service):
    order = purchase(amounts=("120.00", "20.00"))
    order[2][0][1]["custrecord_swc_subpo_item_ratewithrate"] = Decimal("12")
    order[2][1][1]["custrecord_swc_subpo_item_ratewithrate"] = Decimal("2")
    save(ns, engine, bundle([order], [customs("870")]))
    lines = group(service, "CD870").customsLines
    assert [(line.margin, line.marginStatus) for line in lines] == [("-12.68%", "negative"), ("81.22%", "ok")]
    assert lines[0].declaredUnitPriceCny == "10.65" and lines[0].combinedPurchaseUnitPrice == "12"
    assert lines[0].marginNote == "报关单价低于采购价"
    assert lines[0].purchaseLines[0].salesOrderExchangeRate == "7.1"
    set_rate(engine, None)
    lines = group(service, "CD870").customsLines
    assert lines[0].margin == "" and lines[0].marginStatus == "unavailable" and "汇率" in lines[0].marginNote
    assert lines[0].purchaseLines[0].salesOrderExchangeRate == ""
    # 汇率不参与内容摘要：汇率变化不会让报关单需要重审
    assert rows(engine, "SELECT content_sha256 FROM source_customs_declarations")[0]["content_sha256"] == (
        group(service, "CD870").contentSha256
    )


def test_purchase_sales_rate_preserves_precision_and_requires_own_relation(ns, engine, service):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    content = service.declarations.detail(int(group(service, "CD870").id))
    sales_id = content["orders"][0]["sales_order_id"]
    content["sales_orders"][sales_id]["exchange_rate"] = Decimal("6.712345678901")

    def displayed():
        result = declaration(content, "pending", False, None, True, "")
        return result.customsLines[0].purchaseLines[0].salesOrderExchangeRate

    assert displayed() == "6.712345678901"
    # 即使本张报关单已有其他销售订单汇率，也不能借给缺少关联的子采购单。
    content["orders"][0]["sales_order_id"] = None
    assert displayed() == ""
    content["orders"][0]["sales_order_id"] = sales_id
    content["sales_orders"] = {}
    assert displayed() == ""


def price(world, engine, number):
    found = proposals(world, invoice_id(engine, number))[0]
    return found, next(check for check in found.checks if check.key == "price")


def test_invoice_above_declared_price_needs_note_and_blocks_batch(engine, world, reviewed):
    set_rate(engine, Decimal("5"))  # 申报价 15×5=75 元、单价 7.5 元，低于发票不含税 88.94 元、单价 8.894 元
    import_invoices(world, [invoice("26000000000000005501", [INK], remark="SUB-200")])
    found, check = price(world, engine, "26000000000000005501")
    assert check.result == "mismatch" and "不含税总价超出申报价" in check.note and "单价" in check.note
    assert "发票不含税价格高于申报价" in found.noteReasons
    batch = world["allocations"].confirm_batch(BatchBody(ids=[found.id]), USER)
    assert batch["confirmed"] == 0 and batch["skipped"]
    with pytest.raises(ApiError) as error:
        world["allocations"].confirm(int(found.id), ConfirmBody(), USER)
    assert error.value.status == 400 and "高于申报价" in error.value.message
    world["allocations"].confirm(int(found.id), ConfirmBody(note="与销售确认按合同价开票"), USER)
    assert rows(engine, "SELECT status FROM matching_allocations")[0]["status"] == "confirmed"


def test_missing_rate_is_not_an_anomaly(engine, world, reviewed):
    set_rate(engine, None)
    import_invoices(world, [invoice("26000000000000005502", [INK], remark="SUB-200")])
    found, check = price(world, engine, "26000000000000005502")
    assert check.result == "missing" and "汇率" in check.note
    assert not any("申报价" in reason for reason in found.noteReasons)


def test_queue_only_abnormal_or_normal(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000005503", [INK], remark="SUB-200")])
    queries = world["queries"]
    normal = queries.queue(QueueQuery(anomaly="normal"))
    assert normal.total == 1 and normal.rows[0].anomalies == [] and normal.counts["all"] == 1
    assert queries.queue(QueueQuery(anomaly="abnormal")).total == 0
    set_rate(engine, Decimal("5"))
    abnormal = queries.queue(QueueQuery(anomaly="abnormal"))
    assert abnormal.total == 1 and "价格" in abnormal.rows[0].anomalies
    assert queries.queue(QueueQuery(anomaly="normal")).total == 0
    assert queries.queue(QueueQuery()).rows[0].anomalies == abnormal.rows[0].anomalies


def test_sales_rate_read_failure_does_not_block_saving():
    def fail(kind, ids):
        raise ApiError(502, "NS 不可用")

    data = {"purchases": purchase()[0:0] or [purchase()], "warnings": []}
    assert read_sales_orders(SimpleNamespace(relation_rows=fail), data) is None
    assert data["warnings"] == [WARNING]
    reads = []
    found = read_sales_orders(
        SimpleNamespace(
            relation_rows=lambda kind, ids: reads.append((kind, ids)) or [{"id": "90", "tranid": "SO1"}]
        ),
        {"purchases": [purchase()], "warnings": []},
    )
    assert reads == [("sales_headers", ["90"])] and found == {"90": {"id": "90", "tranid": "SO1"}}
