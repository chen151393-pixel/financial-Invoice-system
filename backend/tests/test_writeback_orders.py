"""整单分配与账单汇总：只用合成审核快照，不连接 NS。"""

from copy import deepcopy

import pytest
from backend.core.errors import ApiError
from backend.modules.writeback.dto.task_dto import ConfirmPlan
from backend.modules.writeback.policy.order_policy import expand_orders
from backend.modules.writeback.policy.plan_policy import validate_plan
from backend.modules.writeback.policy.preview_policy import build
from backend.modules.writeback.vo.order_vo import orders, plan_view
from pydantic import ValidationError


def sample():
    from backend.tests.test_writeback_prepare import result

    candidates = result()
    candidates["registrationCheck"] = {"invoiceNumber": "TEST", "records": []}
    bill = candidates["purchaseOrders"][0]["bills"][0]
    bill.update(currency="CNY", availableInvoiceAmount="1000.00")
    source = {
        "subpo_id": "200",
        "order_no": "SUB-1",
        "parent_id": "100",
        "parent_number": "PO-100",
        "vendor_id": "77",
        "currency_id": "1",
        "company_ns_id": "subsidiary:1",
    }
    task = {
        "invoice_no": "TEST",
        "vendor_id": "77",
        "candidates": candidates,
        "snapshot": {
            "invoice": {"invoice_no": "TEST", "invoice_date": "2026-10-29", "amount_including_tax": "100.03"},
            "sources": {
                "10": source,
                "11": {**source},
                "12": {**source, "subpo_id": "201", "order_no": "SUB-2"},
            },
            "allocations": [
                {"id": 1, "purchase_line_id": 10, "amount": "33.33"},
                {"id": 2, "purchase_line_id": 11, "amount": "33.34"},
                {"id": 3, "purchase_line_id": 12, "amount": "33.36"},
            ],
        },
    }
    selection = [{"subPurchaseOrderId": key, "billId": "395762"} for key in ("200", "201")]
    return task, candidates, selection


def test_multiple_children_same_bill_sum_exactly_and_keep_original_evidence():
    task, candidates, selected = sample()
    original = deepcopy(task)
    targets = validate_plan(task, candidates, expand_orders(task, selected))
    payload, preview, _ = build(task, targets, candidates, "test-request")
    assert len(payload["bills"]) == 1
    assert payload["bills"][0]["amount"] == "100.03"
    assert preview[0]["amount"] == "100.03"
    assert [order["amount"] for order in orders(task)] == ["66.67", "33.36"]
    assert len(plan_view(task, {"body": {"allocations": targets}})["orders"]) == 2
    assert task == original


@pytest.mark.parametrize(
    "kind",
    ["missing", "duplicate", "unknown", "over_limit", "wrong_parent", "explicit_other_child", "split_lines"],
)
def test_reject_invalid_whole_order_targets(kind):
    task, candidates, selected = sample()
    bill = candidates["purchaseOrders"][0]["bills"][0]
    if kind == "missing":
        selected.pop()
    elif kind == "duplicate":
        selected.append(selected[0])
    elif kind == "unknown":
        selected[0]["subPurchaseOrderId"] = "999"
    elif kind == "over_limit":
        bill["availableInvoiceAmount"] = "100.02"
    elif kind == "wrong_parent":
        bill["purchaseOrderId"] = "999"
    elif kind == "explicit_other_child":
        bill["subPurchaseOrderId"] = "200"
    else:
        other = {**deepcopy(bill), "billId": "395763"}
        candidates["purchaseOrders"][0]["bills"].append(other)
    with pytest.raises(ApiError):
        targets = expand_orders(task, selected)
        if kind == "split_lines":
            targets[1]["billId"] = "395763"
        validate_plan(task, candidates, targets)


def test_request_rejects_client_amount_and_mixed_target_units():
    from uuid import uuid4

    _, _, selected = sample()
    body = dict(revision=1, requestId=uuid4(), confirmScope=True, evidence="已核实账单归属", orders=selected)
    with pytest.raises(ValidationError):
        ConfirmPlan(**{**body, "orders": [{**selected[0], "amount": "1.00"}]})
    with pytest.raises(ValidationError):
        ConfirmPlan(**{**body, "allocations": [{"allocationId": "1", "billId": "395762", "amount": "33.33"}]})
