"""回写列表状态概况与数据库筛选；隔离合成数据，不调用 NS。"""

from decimal import Decimal

import pytest
from backend.modules.writeback.dto.task_dto import TaskQuery
from backend.modules.writeback.entity import tasks
from backend.modules.writeback.policy.list_policy import GROUP_STATES
from backend.modules.writeback.service.task_service import TaskService
from backend.modules.writeback.vo.task_vo import LABELS
from backend.tests.test_matching import engine as engine
from pydantic import ValidationError
from sqlalchemy import select


@pytest.fixture
def listing(engine):
    from datetime import datetime

    stamp = datetime(2026, 10, 29)
    with engine.begin() as connection:
        for index, state in enumerate(LABELS, 1):
            connection.execute(
                tasks.insert().values(
                    task_no=f"NSWB-list-{index}",
                    invoice_id=index,
                    fingerprint=str(index),
                    ns_account="prod" if index % 2 else "other",
                    vendor_id="77",
                    vendor_name="精确%_供应商" if index == 1 else "其他供应商",
                    invoice_no=f"TEST-INVOICE-{index}",
                    amount=Decimal("100.50"),
                    state=state,
                    reason="合成任务",
                    historical=False,
                    snapshot={
                        "sources": {
                            "10": {"parent_id": "100", "parent_number": "PO%_A", "order_no": "SUB-ONLY"},
                            "11": {"parent_id": "100", "parent_number": "PO%_A"},
                            "12": {"parent_id": "200", "parent_number": "PO-B200"},
                        }
                        if index == 1
                        else {},
                        "invoice": {"remark": "PO-REMARK-ONLY"},
                    },
                    candidates={"purchaseOrders": [{"number": "PO-CANDIDATE-ONLY"}]},
                    revision=1,
                    created_at=stamp,
                    updated_at=stamp,
                )
            )
    return TaskService(engine, "prod")


def test_writeback_counts_cover_all_states_without_page_or_status_filter(listing):
    result = listing.list(TaskQuery(pageSize=1))
    assert result["total"] == 12 and len(result["items"]) == 1 and result["pages"] == 12
    assert result["counts"] == {
        "all": 12,
        "pending": 5,
        "executing": 1,
        "applied": 2,
        "attention": 3,
        "stale": 1,
    }
    assert {option["state"] for option in result["states"]} == set(LABELS)
    assert all(
        option["count"] == 1 and option["label"] == LABELS[option["state"]] for option in result["states"]
    )
    assert set(LABELS) == {state for states in GROUP_STATES.values() for state in states}
    for group, expected in GROUP_STATES.items():
        selected = listing.list(TaskQuery(group=group))
        assert {row["state"] for row in selected["items"]} == set(expected)
        assert selected["total"] == result["counts"][group]
        assert selected["counts"] == result["counts"]


def test_existing_registration_is_listed_as_registered_without_changing_stored_state(engine, listing):
    with engine.connect() as connection:
        before = connection.execute(select(tasks).where(tasks.c.state == "conflict")).mappings().one()
    registered = listing.list(TaskQuery(group="applied", state="conflict"))
    assert registered["total"] == 1
    row = registered["items"][0]
    assert row["state"] == "conflict" and row["stateLabel"] == "NS 已有同号登记"
    assert not row["writeback"]["allowed"]
    assert listing.list(TaskQuery(group="attention", state="conflict"))["total"] == 0
    option = next(item for item in registered["states"] if item["state"] == "conflict")
    assert option["group"] == "applied"
    with engine.connect() as connection:
        after = connection.execute(select(tasks).where(tasks.c.id == before["id"])).mappings().one()
    assert dict(after) == dict(before)


def test_exact_state_and_keyword_share_count_scope_and_escape_sql_wildcards(listing):
    exact = listing.list(TaskQuery(state="unknown"))
    assert exact["total"] == 1 and exact["items"][0]["state"] == "unknown"
    assert exact["counts"]["all"] == 12
    result = listing.list(TaskQuery(keyword="%_"))
    assert result["total"] == result["counts"]["all"] == result["counts"]["pending"] == 1
    assert result["counts"]["attention"] == 0
    assert len(listing.list(TaskQuery(keyword="NSWB-list-12"))["items"]) == 1
    assert len(listing.list(TaskQuery(keyword="TEST-INVOICE-12"))["items"]) == 1
    blocked = listing.list(TaskQuery(keyword="%_", group="attention"))
    assert blocked["total"] == 0 and blocked["counts"]["all"] == 1
    empty = listing.list(TaskQuery(keyword="没有这家供应商"))
    assert empty["items"] == [] and empty["pages"] == 1
    assert all(count == 0 for count in empty["counts"].values())
    assert len(empty["states"]) == 12


def test_status_summary_is_read_only_and_invalid_group_is_rejected(engine, listing):
    with engine.connect() as connection:
        before = connection.execute(select(tasks)).all()
    listing.list(TaskQuery(group="executing"))
    listing.list(TaskQuery(group="attention"))
    with engine.connect() as connection:
        assert connection.execute(select(tasks)).all() == before
    with pytest.raises(ValidationError):
        TaskQuery(group="retry_all")


def test_split_search_combines_fields_and_parent_orders_use_frozen_snapshot(listing):
    combined = listing.list(
        TaskQuery(taskNo="NSWB-list-1", invoiceNo="TEST-INVOICE-1", supplierName="精确", parentOrderNo="PO-B")
    )
    assert combined["total"] == combined["counts"]["all"] == 1
    assert combined["items"][0]["parentOrders"] == [
        {"id": "100", "number": "PO%_A"},
        {"id": "200", "number": "PO-B200"},
    ]
    for field, value in [
        ("taskNo", "TEST-INVOICE-1"),
        ("invoiceNo", "NSWB-list-1"),
        ("supplierName", "TEST-INVOICE-1"),
    ]:
        assert listing.list(TaskQuery(**{field: value}))["total"] == 0
    for number in ["PO%_A", "%_", "PO-B200", "  PO-B200  "]:
        result = listing.list(TaskQuery(parentOrderNo=number, pageSize=1))
        assert result["total"] == result["counts"]["all"] == result["counts"]["pending"] == 1
    for number in ["SUB-ONLY", "PO-CANDIDATE-ONLY", "PO-REMARK-ONLY", "absent' OR 1=1"]:
        assert listing.list(TaskQuery(parentOrderNo=number))["total"] == 0
    assert listing.list(TaskQuery(parentOrderNo="PO-B", group="attention"))["counts"]["all"] == 1
    assert listing.list(TaskQuery(parentOrderNo="PO-B", group="attention"))["total"] == 0
    assert listing.list(TaskQuery(taskNo="NSWB-list-2"))["items"][0]["parentOrders"] == []


def test_mysql_parent_search_is_scoped_and_escaped():
    from backend.modules.writeback.dao.task_dao import parent_order_matches
    from sqlalchemy.dialects import mysql

    query = select(tasks.c.id).where(parent_order_matches("PO%_/", "mysql"))
    compiled = query.compile(dialect=mysql.dialect())
    assert "json_search" in str(compiled).lower()
    assert "$.sources.*.parent_number" in compiled.params.values()
    assert "%PO/%/_//%" in compiled.params.values()
