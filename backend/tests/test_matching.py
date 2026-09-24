"""只读匹配：缺失值不当零，含税校验不使用未税单价，身份范围不降级。"""

from decimal import Decimal as D
from unittest.mock import Mock

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.policy import compare
from backend.modules.matching.service import MatchingService


def source():
    invoice = {"seller": "供应商Ａ"}
    item = {
        "item": "*日用品*保温杯",
        "quantity": "2480",
        "unit": "个",
        "gross": "38522",
        "unitPrice": "13.74336283",
    }
    order = {"supplier_name": "供应商A"}
    line = {
        "item_name": "保温杯",
        "declaration_name": "保温杯",
        "quantity": D("2480"),
        "unit_name": "个",
        "declaration_quantity": D("2480"),
        "declaration_unit": "个",
        "tax_inclusive_price": D("15.53225806"),
        "amount": D("38522"),
    }
    return invoice, item, order, line


def test_no_rounding_tolerance_invented():
    values = source()
    checks = compare(*values)
    assert all(x["matched"] for x in checks)
    values[1]["gross"] = "38514.4"
    assert not compare(*values)[4]["matched"]
    values[3].update(tax_inclusive_price=D("15.53"), amount=D("38514.4"))
    assert all(x["matched"] for x in compare(*values))


@pytest.mark.parametrize("field", ["declaration_quantity", "declaration_unit", "declaration_name", "amount"])
def test_missing_purchase_fields_never_full_match(field):
    values = source()
    values[3][field] = None
    assert not all(x["matched"] for x in compare(*values))


def test_unit_alias_not_implicitly_converted():
    values = source()
    values[3]["declaration_unit"] = "箱"
    assert not compare(*values)[3]["matched"]


def test_invisible_invoice_stops_before_purchase_read():
    invoices, purchases = Mock(), Mock()
    invoices.invoice_detail.side_effect = ApiError(404, "不可见")
    with pytest.raises(ApiError):
        MatchingService(invoices, purchases).preview(1, "user:a")
    purchases.read.assert_not_called()


def test_no_supplier_overlap_and_owner_propagation():
    invoices, purchases = Mock(), Mock()
    invoices.invoice_detail.return_value = {"id": "1", "seller": "A", "lines": []}
    purchases.read.return_value = ([{"id": 2, "supplier_name": "B"}], [])
    result = MatchingService(invoices, purchases).preview(1, "user:a")
    invoices.invoice_detail.assert_called_once_with(1, "user:a")
    purchases.read.assert_called_once_with("user:a")
    assert result["sameSupplierCount"] == 0 and result["candidates"] == []
    assert result["allowed"] is False
