"""票面线索只读核对：验证 NS 来源引用和金额显示，不创建匹配关系。"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from backend.core.errors import ApiError
from backend.modules.business.related_purchase_lookup import RelatedPurchaseLookup
from backend.modules.business.related_purchase_vo import RelatedPurchaseFound, RelatedPurchaseMissing

CONFIG = {
    "pl": {"type": "pl", "number": "name"},
    "purchase": {
        "type": "purchase",
        "pl": "pl",
        "customs": "customs",
        "company": "company",
        "fields": {"purchase": "name", "parent": "parent", "vendor": "vendor"},
        "storage_fields": {"order_date": "date", "total_amount": "total"},
    },
    "purchase_line": {
        "type": "purchase_line",
        "parent": "purchase",
        "fields": {"name": "name", "quantity": "quantity", "amount": "amount"},
    },
    "customs": {
        "type": "customs",
        "fields": {"declaration": "declaration", "date": "date"},
        "storage_fields": {"record_no": "name"},
    },
    "customs_line": {"type": "customs_line", "parent": "parent", "pl": "pl", "company": "company"},
}


class FakeNS:
    def __init__(self):
        self.settings = SimpleNamespace(pl_lookup=deepcopy(CONFIG), record_types=list(CONFIG))
        self.index = {
            ("purchase", "name", "YE-ST251231-Y593-1"): ["548"],
            ("purchase_line", "purchase", "548"): ["9601", "9604"],
        }
        self.data = {
            ("purchase", "548"): {
                "name": "YE-ST251231-Y593-1",
                "parent": {"id": "228739", "refName": "采购订单 #YE-ST251231-Y593"},
                "pl": {"id": "230", "refName": "PL2601220005"},
                "customs": {"id": "252", "refName": "CD000252"},
                "vendor": {"id": "9749", "refName": "义乌市尚图数码影像有限公司"},
                "date": "2026-01-22",
                "total": Decimal("2473.000000"),
            },
            ("purchase_line", "9601"): {
                "purchase": {"id": "548"},
                "name": "胸章机",
                "quantity": 10,
                "amount": Decimal("913.00"),
            },
            ("purchase_line", "9604"): {
                "purchase": {"id": "548"},
                "name": "胸章",
                "quantity": 2000,
                "amount": Decimal("1560.00"),
            },
            ("customs", "252"): {
                "name": "CD000252",
                "declaration": "310120260519278380",
            },
        }
        self.calls = []

    def filtered_ids(self, record_type, field, value, *, reference=False):
        self.calls.append(("ids", record_type, field, value, reference))
        return self.index.get((record_type, field, value), [])

    def request(self, method, record_type, record_id, *, exact_numbers=False):
        self.calls.append((method, record_type, record_id, exact_numbers))
        return {"data": self.data[record_type, record_id]}


def test_exact_source_chain_and_decimal_comparison():
    ns = FakeNS()
    result = RelatedPurchaseLookup(ns).query("YE-ST251231-Y593-1", "2473.00")
    assert result["found"] is True
    assert result["customs"]["recordNo"] == "CD000252"
    assert result["customs"]["declarationNo"] == "310120260519278380"
    assert result["amountMatches"] is True
    assert result["purchaseAmount"] == "2473.000000"
    assert RelatedPurchaseFound.model_validate(result).customs.declarationNo == "310120260519278380"
    assert [row["amount"] for row in result["lines"]] == ["913.00", "1560.00"]
    assert ns.calls[0] == ("ids", "purchase", "name", "YE-ST251231-Y593-1", False)
    assert all(call[0] in ("ids", "GET") for call in ns.calls)


def test_absent_or_ambiguous_order_never_returns_a_match():
    ns = FakeNS()
    result = RelatedPurchaseLookup(ns).query("OTHER", "2473.00")
    assert result["found"] is False
    assert RelatedPurchaseMissing.model_validate(result).found is False
    assert ns.calls == [("ids", "purchase", "name", "OTHER", False)]
    ns.index["purchase", "name", "YE-ST251231-Y593-1"] = ["548", "549"]
    with pytest.raises(ApiError, match="多个同号"):
        RelatedPurchaseLookup(ns).query("YE-ST251231-Y593-1", "2473.00")


def test_source_identity_mismatch_is_rejected_and_amount_mismatch_is_shown():
    ns = FakeNS()
    ns.data["purchase", "548"]["name"] = "OTHER"
    with pytest.raises(ApiError, match="不一致"):
        RelatedPurchaseLookup(ns).query("YE-ST251231-Y593-1", "2473.00")
    ns.data["purchase", "548"]["name"] = "YE-ST251231-Y593-1"
    ns.data["purchase_line", "9601"]["purchase"] = {"id": "another"}
    with pytest.raises(ApiError, match="明细归属"):
        RelatedPurchaseLookup(ns).query("YE-ST251231-Y593-1", "2473.00")
    ns.data["purchase_line", "9601"]["purchase"] = {"id": "548"}
    assert RelatedPurchaseLookup(ns).query("YE-ST251231-Y593-1", "2472.99")["amountMatches"] is False
