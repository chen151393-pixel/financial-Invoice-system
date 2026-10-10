"""NS 来源存储测试共用的假 NS：按配置返回 PL、子采购、报关记录，不调用真实 NS。

由已删除的 PL 联查接口测试中提取；被 test_pl_storage 及依赖它的存储、同步、迁移测试复用。
"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

CONFIG = {
    "pl": {"type": "pl", "number": "name"},
    "purchase": {
        "type": "purchase",
        "pl": "pl",
        "customs": "customs",
        "company": "company",
        "fields": {"purchase": "name"},
    },
    "purchase_line": {"type": "purchase_line", "parent": "parent", "fields": {"amount": "amount"}},
    "customs": {"type": "customs", "fields": {"declaration": "number"}},
    "customs_line": {
        "type": "customs_line",
        "parent": "parent",
        "pl": "pl",
        "company": "company",
        "fields": {"name": "name"},
    },
}


def ref(value):
    return {"id": value}


class LookupNS:
    def __init__(self):
        self.settings = SimpleNamespace(pl_lookup=deepcopy(CONFIG), record_types=list(CONFIG))
        self.calls = []
        self.index = {
            ("pl", "name", "PL001"): ["1"],
            ("purchase", "pl", "1"): ["10", "11"],
            ("purchase_line", "parent", "10"): ["100"],
            ("purchase_line", "parent", "11"): ["101"],
            ("customs_line", "parent", "20"): ["200", "201", "202"],
        }
        self.data = {
            ("purchase", "10"): {"name": "PO1", "pl": ref("1"), "customs": ref("20"), "company": ref("3")},
            ("purchase", "11"): {"name": "PO2", "pl": ref("1"), "customs": ref("20"), "company": ref("3")},
            ("purchase_line", "100"): {"parent": ref("10"), "amount": Decimal("22880.000001")},
            ("purchase_line", "101"): {"parent": ref("11"), "amount": Decimal("1.20")},
            ("customs", "20"): {"number": "CD001"},
            ("customs_line", "200"): {"parent": ref("20"), "pl": ref("1"), "company": ref("3"), "name": "纸"},
            ("customs_line", "201"): {"parent": ref("20"), "pl": ref("9"), "company": ref("3")},
            ("customs_line", "202"): {
                "parent": ref("20"),
                "pl": ref("1"),
                "company": ref("4"),
                "name": "另一公司",
            },
        }

    def validate(self, record_type, record_id):
        assert record_type in self.settings.record_types
        assert record_id.isdigit()

    def filtered_ids(self, record_type, field, value, **kwargs):
        return self.index.get((record_type, field, value), [])

    def request(self, method, record_type, record_id, **kwargs):
        assert method == "GET"
        self.calls.append((record_type, record_id))
        return {"data": self.data[record_type, record_id]}
