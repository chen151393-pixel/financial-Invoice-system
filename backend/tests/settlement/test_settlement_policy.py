"""结汇纯规则：回款路径、差额只认手续费、组合推荐、状态机与可操作判断。"""

from decimal import Decimal

from backend.modules.settlement.policy.amount_policy import balance_check, suggest_combination
from backend.modules.settlement.policy.batch_state_policy import actions, can_transition
from backend.modules.settlement.policy.route_policy import DIRECT, HK_TRANSIT, hk_consignee_keys, route_of

HK = hk_consignee_keys(())


def test_route_prefers_trade_country_then_hk_consignee_list():
    assert route_of("中国香港", "ACME LTD", HK)[0] == HK_TRANSIT
    assert route_of("巴西", "HONGKONG VISION DIGITAL PRINTING CO., LIMITED", HK)[0] == DIRECT
    # 回执未给贸易国时按集团香港公司名单判定，名称比较忽略大小写与空白
    assert route_of("", "hongkong  vision digital printing co., limited", HK) == (
        HK_TRANSIT,
        "境外收货人为集团香港公司",
    )
    assert route_of("", "ACME LTD", HK)[0] == DIRECT
    assert route_of("", "ACME LTD", hk_consignee_keys(["acme ltd"]))[0] == HK_TRANSIT


def test_difference_is_only_explained_by_fee():
    ok = balance_check(Decimal("1000.00"), Decimal("985.00"), Decimal("15.00"), Decimal("50"))
    assert ok == {"balanced": True, "difference": Decimal("0.00"), "warnings": []}
    short = balance_check(Decimal("1000.00"), Decimal("980.00"), Decimal("15.00"), Decimal("50"))
    assert not short["balanced"] and short["difference"] == Decimal("5.00")
    assert short["warnings"] == ["到账加手续费比报关金额少 5.00"]
    over = balance_check(Decimal("1000"), Decimal("920"), Decimal("80"), Decimal("50"))
    assert over["balanced"] and "超过预警上限" in over["warnings"][0]


def test_suggest_combination_finds_exact_sum_in_cents():
    candidates = [("A", "33250.00"), ("B", "8361.36"), ("C", "1000.00"), ("D", "1185.03"), ("E", "360.00")]
    # 8361.36 + 1000.00 + 360.00
    assert sorted(suggest_combination(candidates, Decimal("9721.36"))) == ["B", "C", "E"]
    assert suggest_combination(candidates, Decimal("1.00")) is None
    assert suggest_combination(candidates, Decimal("0")) is None
    # 不超过目标金额的候选超过 40 张时不做组合搜索，交给人工勾选
    assert suggest_combination([(f"X{i}", "0.01") for i in range(60)], Decimal("0.50")) is None


def _batch(route, status):
    return {"route": route, "status": status}


def test_hk_transit_requires_documents_before_remittance():
    assert can_transition(HK_TRANSIT, "collected", "documents_ready")
    assert not can_transition(HK_TRANSIT, "collected", "settled")
    assert not can_transition("direct", "collected", "documents_ready")
    collected = actions(_batch(HK_TRANSIT, "collected"), True, None)
    assert collected["documentsReady"]["allowed"] and not collected["settle"]["allowed"]
    unbalanced = actions(_batch(HK_TRANSIT, "collected"), False, None)
    assert "不一致" in unbalanced["documentsReady"]["reason"]
    ready = actions(_batch(HK_TRANSIT, "documents_ready"), True, None)
    assert ready["settle"]["allowed"] and ready["cancel"]["allowed"]


def test_direct_settles_only_when_balanced_and_settled_cannot_cancel():
    assert actions(_batch(DIRECT, "collected"), True, None)["settle"]["allowed"]
    assert not actions(_batch(DIRECT, "collected"), False, None)["settle"]["allowed"]
    settled = actions(_batch(DIRECT, "settled"), True, None)
    assert not settled["cancel"]["allowed"] and not settled["settle"]["allowed"]
    assert not settled["documentsReady"]["allowed"]
