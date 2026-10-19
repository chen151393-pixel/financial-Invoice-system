"""明细保存与票头补全：严格金额、版本去重、重排及异常原子回滚。"""

from copy import deepcopy

import pytest
from backend.modules.invoice.entity import headers, items, versions
from backend.tests.sync.lemon_detail_fixtures import full_invoice
from backend.tests.sync.test_lemon_invoices import BASE, body, count
from backend.tests.sync.test_lemon_invoices import setup as setup
from sqlalchemy import select


def pull(world):
    return world.client.post(BASE + "/invoices/pull-save", json=body())


def test_header_completion_repeat_and_reordering_keep_ids(setup):
    assert pull(setup).json()["result"]["pendingDetails"] == 1
    setup.upstream.rows = [full_invoice()]
    result = pull(setup).json()["result"]
    assert result["updated"] == result["completeDetails"] == 1 and result["pendingDetails"] == 0
    with setup.engine.connect() as connection:
        original = connection.execute(select(items)).mappings().one()
        assert str(original["tax_rate"]) == "0.130000"
        assert str(original["amount_including_tax"]) == "113.00"
    assert pull(setup).json()["result"]["unchanged"] == 1
    assert count(setup.engine, headers) == 1 and count(setup.engine, versions) == 2
    setup.upstream.rows[0]["Detail"]["invoiceEntries"][0]["sn"] = 99
    assert pull(setup).json()["result"]["unchanged"] == 1
    with setup.engine.connect() as connection:
        assert connection.scalar(select(items.c.id)) == original["id"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("number", "wrong"),
        ("number", 1),
        ("invoiceId", True),
        ("invoiceId", 3),
        ("invoiceType", 1000),
        ("code", "123"),
        ("invoiceDate", "2026-10-11"),
        ("amount", "99"),
        ("tax", "12"),
        ("name", "另一供应商"),
        ("isInvalid", 1),
        ("businessType", 2),
        ("note", "different"),
        ("invoiceEntries", None),
        ("invoiceEntries", [None]),
    ],
)
def test_identity_changes_or_missing_detail_roll_back_batch(setup, field, value):
    setup.upstream.rows = [full_invoice(), full_invoice(InvoiceId=2, Number="2")]
    setup.upstream.rows[-1]["Detail"][field] = value
    response = pull(setup)
    assert response.status_code == 422, response.text
    assert count(setup.engine, headers) == count(setup.engine, items) == count(setup.engine, versions) == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("quality", "1.000000001"),
        ("quality", "NaN"),
        ("quality", True),
        ("quality", "1000000000000000000"),
        ("amount", "99.99"),
        ("amount", "1.001"),
        ("tax", "12.99"),
        ("tax", "Infinity"),
        ("taxRate", "101"),
        ("name", 123),
        ("unit", ["个"]),
        ("model", "x" * 501),
    ],
)
def test_invalid_entry_precision_totals_and_text_rejected(setup, field, value):
    setup.upstream.rows = [full_invoice()]
    setup.upstream.rows[0]["Detail"]["invoiceEntries"][0][field] = value
    response = pull(setup)
    assert response.status_code == 422, response.text
    assert count(setup.engine, versions) == 0


@pytest.mark.parametrize("field", ["quality", "unit", "name"])
def test_missing_matching_fields_stay_pending_then_complete(setup, field):
    raw = full_invoice()
    raw["Detail"]["invoiceEntries"][0][field] = None
    setup.upstream.rows = [raw]
    result = pull(setup).json()["result"]
    assert result["completeDetails"] == 0 and result["pendingDetails"] == 1
    assert pull(setup).json()["result"]["unchanged"] == 1
    setup.upstream.rows = [full_invoice()]
    assert pull(setup).json()["result"]["completeDetails"] == 1


def test_empty_details_preserve_old_projection_without_version_churn(setup):
    setup.upstream.rows = [full_invoice()]
    assert pull(setup).status_code == 200
    setup.upstream.rows[0]["Detail"]["invoiceEntries"] = []
    assert pull(setup).json()["result"]["pendingDetails"] == 1
    assert count(setup.engine, items) == 1
    assert pull(setup).json()["result"]["unchanged"] == 1
    assert count(setup.engine, versions) == 2


def test_duplicate_identity_changes_remain_under_review_and_idempotent(setup):
    raw = full_invoice()
    line = raw["Detail"]["invoiceEntries"][0]
    line.update(amount="50", tax="6.5", quality="5")
    raw["Detail"]["invoiceEntries"].append(deepcopy(line))
    setup.upstream.rows = [raw]
    assert pull(setup).status_code == 200
    assert pull(setup).json()["result"]["unchanged"] == 1
    line["quality"] = "6"
    assert pull(setup).json()["result"]["pendingDetails"] == 1
    assert pull(setup).json()["result"]["unchanged"] == 1
    with setup.engine.connect() as connection:
        assert connection.scalar(select(headers.c.detail_status)) == "failed"


@pytest.mark.parametrize("rate", ["-100", "-101", "0"])
def test_tax_exemption_codes_preserved_without_invented_rate(setup, rate):
    raw = full_invoice(Tax="0", AdValoremTaxTotals="100")
    raw["Detail"]["invoiceEntries"][0]["taxRate"] = rate
    setup.upstream.rows = [raw]
    assert pull(setup).status_code == 200
    with setup.engine.connect() as connection:
        actual = connection.scalar(select(items.c.tax_rate))
        assert actual == (0 if rate == "0" else None)
