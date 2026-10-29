"""发票备注的关联销售单号与含税合计回归，使用隔离 SQLite 和合成数据。"""

from decimal import Decimal

import pytest
from backend.modules.matching.dto.matching_dto import CandidateQuery
from backend.modules.matching.policy.allocation_policy import note_reasons
from backend.modules.matching.policy.comparison_policy import order_reference
from backend.modules.matching.policy.group_comparison_policy import compare_group
from backend.modules.source.public import purchase_lines
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import rows
from sqlalchemy import text


@pytest.mark.parametrize(
    ("remark", "expected"),
    [
        ("请购单号：VIE260529-01 订单编号:1", True),
        ("请购单号：ｖｉｅ２６０５２９－０１", True),
        ("VIE260529-010", False),
        ("VIE260529-01-1", False),
        ("PREFIX-VIE260529-01", False),
        ("VIE260529-02", False),
        ("", False),
    ],
)
def test_sales_order_requires_complete_number(remark, expected):
    line = {"sales_order_no": "销售订单 #VIE260529-01"}
    reference = order_reference(remark, line)
    assert bool(reference) is expected
    if expected:
        assert reference == ("销售订单", "VIE260529-01")
    assert order_reference(remark, {"sales_order_no": None}) is None


def test_screenshot_compares_gross_and_recognizes_sales_reference():
    bill = {
        "remark": "请购单号：VIE260529-01 订单编号:1",
        "seller_name": "东莞市创远智能设备有限公司",
        "buyer_name": None,
        "buyer_name_normalized": None,
    }
    item = {
        "item_name": "*纺织专用设备*迷你烫画机",
        "unit": "台",
        "quantity": Decimal(120),
        "amount_excluding_tax": Decimal("7523.89"),
        "amount_including_tax": Decimal("8502"),
    }
    line = {
        "order_no": "YE-CY20260603-P80-1",
        "parent_order_no": "采购订单 #YE-CY20260603-P80",
        "sales_order_no": "销售订单 #VIE260529-01",
        "supplier_name": bill["seller_name"],
        "company_name": "采购公司",
        "company_name_normalized": "采购公司",
        "item_name": "迷你烫画机",
        "unit_name": "台",
        "tax_rate": None,
        "declared": {"amount_cny": Decimal("8652.46")},
    }
    parts = [(line, Decimal(120), Decimal(8502))]
    checks, _ = compare_group(bill, item, Decimal("978.11"), parts)
    by_key = {check["key"]: check for check in checks}
    assert by_key["order"]["result"] == "match"
    assert "备注命中销售订单 VIE260529-01" in by_key["order"]["note"]
    assert by_key["amount"]["label"] == "合计金额"
    assert by_key["amount"]["invoiceValue"] == by_key["amount"]["purchaseValue"] == "8502"
    assert by_key["amount"]["result"] == "match"
    assert "price" not in by_key
    # 金额相同不能替代订单关联；组内任一子单未命中仍提示不一致。
    unrelated = {**line, "order_no": "OTHER", "sales_order_no": "VIE260529-02"}
    checks, _ = compare_group(bill, item, None, parts + [(unrelated, Decimal(0), Decimal(0))])
    assert next(check for check in checks if check["key"] == "order")["result"] == "mismatch"


def test_sales_relation_survives_import_candidate_and_group_query(engine, world, reviewed):
    with engine.begin() as connection:
        connection.execute(text("UPDATE source_sales_orders SET order_no = 'VIE260529-01'"))
    number = "26000000000000009521"
    import_invoices(world, [invoice(number, [INK, FLUID], remark="请购单号：VIE260529-01 订单编号:1")])
    target = invoice_id(engine, number)
    view = world["queries"].invoice(target)
    (group,) = view.groups
    assert all(next(c for c in item.checks if c.key == "order").result == "match" for item in group.items)
    assert not group.noteReasons
    result = world["queries"].candidates(
        CandidateQuery(invoiceId=str(target), invoiceItemId=view.items[0].id)
    )
    assert result.rows
    assert all(next(c for c in row.checks if c.key == "order").result == "match" for row in result.rows)
    # 缺失关联不能借用其他销售单，也不能回退到报关单上不明确的销售单。
    with engine.begin() as connection:
        connection.execute(text("UPDATE source_purchase_orders SET sales_order_id = NULL"))
    group = world["queries"].invoice(target).groups[0]
    assert all(next(c for c in item.checks if c.key == "order").result == "mismatch" for item in group.items)


def test_sales_reference_is_account_scoped_and_does_not_expire_existing_digest(engine, reviewed):
    ids = [row["id"] for row in rows(engine, "SELECT id FROM source_purchase_order_lines")]
    with engine.begin() as connection:
        original = purchase_lines(connection, ids)
        assert all(line["sales_order_no"] == "SO1" for line in original.values())
        connection.execute(text("UPDATE source_sales_orders SET ns_account = 'another-account'"))
        changed = purchase_lines(connection, ids)
        assert all(line["sales_order_no"] is None for line in changed.values())
        assert {key: line["digest"] for key, line in original.items()} == {
            key: line["digest"] for key, line in changed.items()
        }


def test_retired_price_snapshot_does_not_require_a_note():
    assert not note_reasons(
        [{"key": "price", "label": "申报价", "result": "mismatch", "invoiceValue": "100"}],
        False,
        False,
    )
