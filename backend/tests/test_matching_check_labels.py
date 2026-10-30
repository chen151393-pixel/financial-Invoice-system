"""比对项展示文字：分次收票不再显示为“一致”，历史快照同样适用。"""

import pytest
from backend.modules.matching.mapper.allocation_mapper import check_views
from backend.modules.matching.policy.check_label_policy import check_labels


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        # 截图场景：发票 72 台 / 5101.2 元，剩余应开 192 台 / 15068.16 元
        ({"key": "quantity", "result": "match", "difference": "-120"}, ("分次收票", "收票后剩余应开 120")),
        ({"key": "amount", "result": "match", "difference": "-9966.96"}, ("分次收票", "收票后剩余应开 9966.96")),
        ({"key": "amount", "result": "match", "difference": "-100.5"}, ("分次收票", "收票后剩余应开 100.50")),
        ({"key": "quantity", "result": "match", "difference": "0"}, ("一致", None)),
        ({"key": "amount", "result": "match", "difference": "0.00"}, ("一致", None)),
        # 金额容差内仍为一致，不当作分次收票
        ({"key": "amount", "result": "match", "difference": "-0.01"}, ("一致", "差额 -0.01，在 0.01 元容差内")),
        ({"key": "amount", "result": "match", "difference": "0.01"}, ("一致", "差额 0.01，在 0.01 元容差内")),
        ({"key": "quantity", "result": "mismatch", "difference": "30"}, ("不一致", "发票多 30")),
        ({"key": "amount", "result": "mismatch", "difference": "-12.3"}, ("不一致", "发票少 12.30")),
        ({"key": "quantity", "result": "mismatch", "difference": None}, ("不一致", None)),
        ({"key": "seller", "result": "partial", "difference": None}, ("部分一致", None)),
        ({"key": "buyer", "result": "missing", "difference": None}, ("未提供", None)),
    ],
)
def test_labels(check, expected):
    assert check_labels(check) == expected


def test_stored_snapshot_without_label_fields_gets_labels():
    stored = {
        "key": "quantity",
        "label": "数量",
        "invoiceValue": "72",
        "purchaseValue": "192",
        "result": "match",
        "difference": "-120",
        "note": "本次数量在剩余应开范围内可分次收票；不同单位须核实换算",
        "score": "15",
    }
    view = check_views([stored])[0]
    assert view.result == "match" and view.difference == "-120"
    assert (view.resultLabel, view.differenceLabel) == ("分次收票", "收票后剩余应开 120")
