"""进项发票按匹配状态筛选：判定策略、计数与筛选、分页、与单张摘要一致、HTTP 校验。"""

from decimal import Decimal

import pytest
from backend.app import create_app
from backend.modules.matching.dto.invoice_list_dto import InvoiceListQuery
from backend.modules.matching.dto.matching_dto import ConfirmBody, SummaryBody
from backend.modules.matching.policy.invoice_match_policy import match_status
from backend.modules.matching.service.invoice_list_service import InvoiceListService
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_task import USER
from fastapi.testclient import TestClient
from pydantic import ValidationError

MATCHED = "26000000000000007701"
OTHER = "26000000000000007702"
VOID = "26000000000000007703"


def allocation(status, item=1, valid=True, confidence=None):
    return {
        "status": status,
        "invoice_item_id": item,
        "verification_status": "valid" if valid else "invalidated",
        "confidence": confidence,
    }


def test_policy_order_and_labels():
    assert match_status("normal", [], 2)["status"] == "none"
    proposed = match_status("normal", [allocation("proposed", confidence=Decimal(90))], 2)
    assert (proposed["status"], proposed["label"], proposed["best_confidence"]) == ("proposed", "待审核", 90)
    assert match_status("normal", [allocation("confirmed", 1)], 2)["status"] == "partial"
    full = [allocation("confirmed", 1), allocation("confirmed", 2)]
    assert match_status("normal", full, 2)["label"] == "已匹配"
    assert match_status("normal", [], 0)["status"] == "none"  # 没有有效行不算已匹配
    assert match_status("void", full, 2)["label"] == "不参与比对"
    assert match_status("red_letter", [], 1)["status"] == "excluded"
    # 复核失效的占用优先提示，作废发票也不隐藏
    assert match_status("void", [allocation("confirmed", valid=False)], 1)["label"] == "待复核"


def query(**values):
    return InvoiceListQuery(**values)


@pytest.fixture
def listed(engine, world, reviewed):
    import_invoices(
        world,
        [
            invoice(MATCHED, [INK, FLUID], remark="SUB-200"),
            invoice(OTHER, [("无关商品", "个", "1", "5.00", "0.65")], seller="无关贸易有限公司"),
            invoice(VOID, [("作废商品", "个", "1", "8.00", "1.04")], status="作废"),
        ],
    )
    return InvoiceListService(engine)


def numbers(result):
    return [row.number for row in result.list.rows]


def test_counts_filter_and_summaries(engine, world, listed):
    everything = listed.query(query())
    assert everything.counts == {
        "all": 3,
        "confirmed": 0,
        "partial": 0,
        "proposed": 1,
        "needs_review": 0,
        "none": 1,
        "excluded": 1,
    }
    assert everything.list.total == 3 and not everything.notice
    assert [row.label for row in everything.summaries] == [
        {MATCHED: "待审核", OTHER: "未匹配", VOID: "不参与比对"}[number] for number in numbers(everything)
    ]
    waiting = listed.query(query(matchStatus="proposed"))
    assert numbers(waiting) == [MATCHED] and waiting.list.total == 1
    assert waiting.counts == everything.counts  # 张数不随所选匹配状态变化
    assert waiting.list.amounts[0].count == 1  # 票面汇总按筛选后的范围
    assert numbers(listed.query(query(matchStatus="excluded"))) == [VOID]
    # 与其他条件取交集；空结果不报错
    assert listed.query(query(matchStatus="proposed", q=OTHER)).list.total == 0
    assert listed.query(query(matchStatus="confirmed")).list.rows == []
    # 与单张摘要接口结果一致
    single = world["queries"].summaries(SummaryBody(invoiceIds=[str(invoice_id(engine, VOID))])).rows[0]
    assert (single.status, single.label) == ("excluded", "不参与比对")


def test_progress_through_partial_confirmed_and_review(engine, world, listed):
    first, second = proposals(world, invoice_id(engine, MATCHED))
    world["allocations"].confirm(int(first.id), ConfirmBody(), USER)
    assert numbers(listed.query(query(matchStatus="partial"))) == [MATCHED]
    world["allocations"].confirm(int(second.id), ConfirmBody(), USER)
    done = listed.query(query(matchStatus="confirmed"))
    assert numbers(done) == [MATCHED] and done.summaries[0].label == "已匹配"
    import_invoices(world, [invoice(MATCHED, [INK, FLUID], remark="SUB-200 换版")], name="changed.xlsx")
    review = listed.query(query(matchStatus="needs_review"))
    assert numbers(review) == [MATCHED] and review.counts["needs_review"] == 1


def test_pagination_inside_selected_status(engine, world, listed):
    page = listed.query(query(matchStatus="all", page_size=2, page=2))
    assert page.list.total == 3 and len(page.list.rows) == 1 and page.list.hasPrevious
    assert len(page.summaries) == 1


def test_validation_and_http(context, engine, world, listed):
    with pytest.raises(ValidationError):
        query(matchStatus="unknown")
    with pytest.raises(ValidationError):
        query(date_from="2026-10-10", date_to="2026-10-01")
    app = create_app(context.settings, context.ns, engine)
    with TestClient(app) as client:
        assert client.post("/api/matching/invoices/query", json={}).status_code == 401
        headers = {"Origin": context.settings.origin}
        client.post(
            "/api/session",
            headers=headers,
            json={"username": "admin", "password": context.settings.admin_password},
        )
        response = client.post("/api/matching/invoices/query", json={"matchStatus": "none"}, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["counts"]["all"] == 3 and [row["number"] for row in body["list"]["rows"]] == [OTHER]
        bad = client.post("/api/matching/invoices/query", json={"matchStatus": "x"}, headers=headers)
        assert bad.status_code == 400  # 项目统一把参数校验失败返回为 400
