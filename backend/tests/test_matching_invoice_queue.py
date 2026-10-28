"""整票审核队列：多明细不跨页，按整票最低分与异常筛选，审核后刷新。"""

import pytest
from backend.modules.matching.dto.matching_dto import ConfirmBody, QueueQuery
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, USER, import_invoices
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from pydantic import ValidationError


def test_invoice_queue_groups_before_paging(engine, world, reviewed):
    import_invoices(
        world,
        [
            invoice("26000000000000009901", [INK, FLUID], remark="SUB-200"),
            invoice("26000000000000009902", [INK]),
            invoice("26000000000000009903", [("其他商品", "箱", "1000", "100000", "0")]),
        ],
    )
    first = world["queries"].invoice_queue(QueueQuery(pageSize=1))
    second = world["queries"].invoice_queue(QueueQuery(pageSize=1, page=2))
    assert first.total == first.pages == 3
    assert first.counts == {"all": 3, "high": 1, "medium": 1, "low": 1}
    assert first.rows[0].proposalCount == 2
    assert first.rows[0].invoice.number == "26000000000000009901"
    assert first.rows[0].invoice.id != second.rows[0].invoice.id
    assert first.rows[0].batch.allowed and len(first.rows[0].batchIds) == 2
    assert not second.rows[0].batch.allowed
    assert world["queries"].invoice_queue(QueueQuery(tier="high")).total == 1
    assert world["queries"].invoice_queue(QueueQuery(page=99)).page == 1


def test_invoice_queue_minimum_tier_and_whole_invoice_anomaly(world, reviewed):
    import_invoices(
        world,
        [invoice("26000000000000009911", [INK, ("未知品名", "箱", "10", "17.70", "2.30")], remark="SUB-200")],
    )
    result = world["queries"].invoice_queue(QueueQuery(anomaly="abnormal"))
    row = result.rows[0]
    assert result.total == 1 and row.proposalCount == 2
    assert row.tier != "high"
    assert "单位" in row.anomalies and not row.batch.allowed and row.batchIds == []
    assert world["queries"].invoice_queue(QueueQuery(anomaly="normal")).total == 0
    assert world["queries"].invoice_queue(QueueQuery(supplierId="999999")).total == 0
    assert (
        world["queries"].invoice_queue(QueueQuery(invoiceFrom="2000-01-01", invoiceTo="2000-01-02")).total
        == 0
    )


def test_invoice_queue_refresh_after_confirmation(world, reviewed):
    import_invoices(world, [invoice("26000000000000009921", [INK, FLUID], remark="SUB-200")])
    first = world["queries"].invoice_queue(QueueQuery()).rows[0]
    world["allocations"].confirm(int(first.batchIds[0]), ConfirmBody(), USER)
    remaining = world["queries"].invoice_queue(QueueQuery())
    assert remaining.total == 1 and remaining.rows[0].proposalCount == 1
    assert remaining.rows[0].batchIds == first.batchIds[1:]
    world["allocations"].confirm(int(first.batchIds[1]), ConfirmBody(), USER)
    empty = world["queries"].invoice_queue(QueueQuery())
    assert empty.total == 0 and empty.rows == [] and empty.counts["all"] == 0


def test_invoice_number_and_supplier_bulk_search_before_paging(world, reviewed):
    import_invoices(
        world,
        [
            invoice("26000000000000009931", [INK, FLUID], remark="SUB-200"),
            invoice("26000000000000009932", [INK]),
            invoice("26000000000000009933", [FLUID]),
        ],
    )

    def browse(**values):
        return world["queries"].invoice_queue(QueueQuery(**values))

    result = browse(invoiceNo="9931，9932;9931\n", supplierName="不存在;上海", pageSize=1, page=2)
    assert result.total == result.counts["all"] == 2 and result.pages == 2
    assert len(result.rows) == 1
    whole = browse(invoiceNo="9931", supplierName="上海").rows[0]
    assert whole.invoice.number.endswith("9931") and whole.proposalCount == 2
    assert browse(invoiceNo="9931", supplierName="不存在").total == 0
    assert browse(invoiceNo="不存在", supplierName="上海").total == 0
    assert browse(supplierName="上海", supplierId="999999").total == 0
    assert browse(invoiceNo="9931", invoiceFrom="2000-01-01", invoiceTo="2000-01-02").total == 0
    assert browse(invoiceNo="9931", invoiceFrom="2026-10-10", invoiceTo="2026-10-10").total == 1
    assert browse(invoiceNo="9931", anomaly="normal", tier="high").total == 1
    for field in ("invoiceNo", "supplierName"):
        assert browse(**{field: "%"}).total == 0
        assert browse(**{field: "_"}).total == 0
    assert browse(invoiceNo="，；\n ").total == 3
    # 保留的逐建议接口使用相同搜索范围，不能接受新字段却忽略它。
    assert world["queries"].queue(QueueQuery(invoiceNo="9931", supplierName="上海")).total == 2
    assert world["queries"].queue(QueueQuery(invoiceNo="不存在")).total == 0


@pytest.mark.parametrize("field", ["invoiceNo", "supplierName"])
def test_queue_bulk_search_validation(field):
    assert getattr(QueueQuery(**{field: " 甲,乙；甲\n "}), field) == "甲\n乙"
    for value in ("x" * 121, ";".join(str(i) for i in range(51))):
        with pytest.raises(ValidationError):
            QueueQuery(**{field: value})
