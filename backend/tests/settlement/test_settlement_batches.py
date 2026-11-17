"""结汇批次用例：海关回执金额 → 候选与路径判定 → 建批次 → 香港中转两段对账 / 直接收汇对平 → 作废释放。"""

import uuid
from decimal import Decimal

import pytest
from backend.core.errors import ApiError
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.dto.batch_dto import (
    BatchQuery,
    CancelRequest,
    CandidateQuery,
    CreateBatchRequest,
    RemittanceRequest,
)
from backend.modules.settlement.service.batch_service import BatchService
from backend.modules.settlement.service.candidate_service import CandidateService
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns

HK = "HONGKONG VISION DIGITAL PRINTING CO., LIMITED"


def services(engine):
    candidates = CandidateService(engine, fee_alert=Decimal("50"))
    return candidates, BatchService(engine, candidates, fee_alert=Decimal("50"))


@pytest.fixture
def seeded(schema_engine, ns):
    """NS 报关单 CD870/CD871/CD872，海关回执：两张香港中转、一张直接收汇、一张 NS 中没有。"""
    save(
        ns,
        schema_engine,
        bundle(
            [purchase("200", "870"), purchase("201", "871"), purchase("202", "872")],
            [customs("870"), customs("871"), customs("872")],
        ),
    )
    _import(
        CustomsReceiptService(schema_engine),
        [
            row("REAL870", "01", "墨水", "个", 10, HK, total=600),
            row("REAL871", "01", "墨水", "个", 10, HK, total=400.5),
            row("REAL872", "01", "墨水", "个", 10, "ACME LTD", total=1000),
            row("REAL999", "01", "相纸", "千克", 1, HK, total=50),
        ],
    )
    return schema_engine


def create(batches, numbers, amount, fee="0", **extra):
    body = {
        "requestId": str(uuid.uuid4()),
        "declarationNos": numbers,
        "receivedOn": "2026-11-10",
        "receivedAmount": amount,
        "receivedFee": fee,
        **extra,
    }
    return batches.create(CreateBatchRequest.model_validate(body), "finance-user")


def test_candidates_split_routes_and_suggest_combination(seeded):
    candidates, _ = services(seeded)
    result = candidates.query(CandidateQuery(consignee="HONGKONG VISION", targetAmount="1000.50"))
    by_no = {item.declarationNo: item for item in result.items}
    # NS 中没有的回执不参与结汇
    assert set(by_no) == {"REAL870", "REAL871"}
    assert by_no["REAL870"].route == "hk_transit" and by_no["REAL870"].recordNo == "CD870"
    assert by_no["REAL871"].amount == "400.50" and by_no["REAL870"].salesOrders == ["YEX260827"]
    assert sorted(result.suggestion) == ["REAL870", "REAL871"]
    direct = candidates.query(CandidateQuery(route="direct")).items
    assert [(i.declarationNo, i.routeLabel) for i in direct] == [("REAL872", "直接收汇")]
    totals = {
        (t.route, t.currency): (t.count, t.amount) for t in candidates.query(CandidateQuery()).unsettled
    }
    assert totals == {("direct", "USD"): (1, "1000.00"), ("hk_transit", "USD"): (2, "1000.50")}


def test_hk_transit_batch_two_stage_reconciliation(seeded):
    candidates, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "985.50", fee="15.00", payer="Brazil Buyer")
    assert (batch.route, batch.status, batch.statusLabel) == ("hk_transit", "collected", "香港已收")
    assert batch.declaredTotal == "1000.50" and batch.balances[0].balanced
    assert batch.batchNo.startswith("SB") and [i.recordNo for i in batch.items] == ["CD870", "CD871"]
    assert batch.actions.documentsReady.allowed and not batch.actions.settle.allowed

    # 已在批次中的报关单不能再选
    blocked = {i.declarationNo: i for i in candidates.query(CandidateQuery()).items}["REAL870"]
    assert blocked.blockedReason.startswith("已在结汇批次") and blocked.batchNo == batch.batchNo
    with pytest.raises(ApiError, match="不能结汇"):
        create(batches, ["REAL870"], "600")

    with pytest.raises(ApiError, match="先确认资料已出"):
        batches.remit(
            batch.id,
            RemittanceRequest.model_validate({"remittedOn": "2026-11-12", "remittedAmount": "990"}),
            "u",
        )
    ready = batches.documents_ready(batch.id, "finance-user")
    assert ready.status == "documents_ready" and ready.documentsReadyBy == "finance-user"

    # 汇回差 0.50：差额不能被当作手续费，拒绝结汇
    with pytest.raises(ApiError, match="少 0.50"):
        batches.remit(
            batch.id,
            RemittanceRequest.model_validate(
                {"remittedOn": "2026-11-12", "remittedAmount": "990", "remittedFee": "10"}
            ),
            "finance-user",
        )
    settled = batches.remit(
        batch.id,
        RemittanceRequest.model_validate(
            {
                "remittedOn": "2026-11-12",
                "remittedAmount": "990.50",
                "remittedFee": "10",
                "remittedReference": "HK-01",
            }
        ),
        "finance-user",
    )
    assert settled.status == "settled" and [b.stage for b in settled.balances] == ["received", "remitted"]
    assert all(b.balanced for b in settled.balances) and not settled.actions.cancel.allowed


def test_direct_batch_and_cancel_releases_declarations(seeded):
    _, batches = services(seeded)
    with pytest.raises(ApiError, match="境外收货人必须一致|回款路径必须一致"):
        create(batches, ["REAL870", "REAL872"], "1600")
    short = create(batches, ["REAL872"], "980", fee="10")
    assert short.route == "direct" and not short.balances[0].balanced
    assert short.actions.settle.reason == "到账加手续费与报关合计不一致，不能确认结汇"
    with pytest.raises(ApiError, match="不一致"):
        batches.settle(short.id, "finance-user")
    with pytest.raises(ApiError, match="仅香港中转"):
        batches.documents_ready(short.id, "finance-user")

    cancelled = batches.cancel(short.id, CancelRequest(reason="金额录错"), "finance-user")
    assert cancelled.status == "cancelled" and cancelled.cancelReason == "金额录错"
    again = create(batches, ["REAL872"], "990", fee="10")
    assert batches.settle(again.id, "finance-user").statusLabel == "已结汇"

    listing = batches.browse(BatchQuery(status="all", declarationNo="REAL872"))
    assert listing.total == 2
    assert {(c.route, c.status): c.count for c in listing.counts} == {
        ("direct", "cancelled"): 1,
        ("direct", "settled"): 1,
    }
    assert batches.browse(BatchQuery()).total == 0  # 默认只看未完结


def test_create_is_idempotent_and_service_identity_is_read_only(seeded):
    _, batches = services(seeded)
    body = CreateBatchRequest.model_validate(
        {
            "requestId": str(uuid.uuid4()),
            "declarationNos": ["REAL872"],
            "receivedOn": "2026-11-10",
            "receivedAmount": "1000",
        }
    )
    first = batches.create(body, "finance-user")
    assert batches.create(body, "finance-user").id == first.id
    with pytest.raises(ApiError, match="服务身份只读"):
        batches.create(body, "service:robot")
    with pytest.raises(ValueError, match="最多两位小数"):
        CreateBatchRequest.model_validate({**body.model_dump(mode="json"), "receivedAmount": "1.005"})
