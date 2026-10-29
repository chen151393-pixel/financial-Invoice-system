"""申报幅度提醒与可自动审核预判（纯函数）。"""

from decimal import Decimal

from backend.modules.review.policy.auto_review_policy import auto_review_reasons, margin_alert

OK = {"status": "ok", "margin": Decimal("5"), "note": ""}
NEGATIVE = {"status": "negative", "margin": Decimal("-3"), "note": "申报单价低于采购折算报关单价"}
UNAVAILABLE = {"status": "unavailable", "margin": None, "note": "报关行与子采购行单位不一致，不计算申报幅度"}
ROWS = [{"amount": Decimal("100")}, {"amount": Decimal("20")}]


def test_all_conditions_met_is_eligible():
    assert auto_review_reasons("pending", False, 0, ROWS, True, [OK, OK]) == []


def test_each_condition_blocks_with_reason():
    assert auto_review_reasons("approved", False, 0, ROWS, True, [OK]) == ["不是待审核状态"]
    assert "来源在上次审核后已变化，需人工重审" in auto_review_reasons("pending", True, 0, ROWS, True, [OK])
    assert "1 条子采购行未关联报关行" in auto_review_reasons("pending", False, 1, ROWS, True, [OK])
    missing = [{"amount": None}]
    assert "子采购含税金额缺失" in auto_review_reasons("pending", False, 0, missing, True, [OK])
    assert "子采购币种待核实" in auto_review_reasons("pending", False, 0, ROWS, False, [OK])
    assert "没有关联的子采购行" in auto_review_reasons("pending", False, 0, [], True, [OK])
    assert "没有报关行" in auto_review_reasons("pending", False, 0, ROWS, True, [])


def test_margin_negative_alerts_and_unavailable_blocks():
    assert margin_alert([OK, NEGATIVE]) and not margin_alert([OK, UNAVAILABLE])
    reasons = auto_review_reasons("pending", False, 0, ROWS, True, [OK, NEGATIVE, UNAVAILABLE])
    assert "采购折算报关单价高于人民币申报单价且超出容差" in reasons
    assert "申报幅度无法计算：报关行与子采购行单位不一致，不计算申报幅度" in reasons
