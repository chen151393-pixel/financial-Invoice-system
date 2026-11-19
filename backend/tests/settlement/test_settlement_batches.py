"""结汇批次用例：海关回执金额 → 候选与路径判定 → 香港中转建批次与两段对账 → 作废释放；
直接收汇不建批次，此前已建的直接收汇批次仍可结汇。"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from backend.core.errors import ApiError
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.dao import batch_dao, batch_item_dao
from backend.modules.settlement.dto.batch_dto import (
    BatchQuery,
    CancelRequest,
    CandidateQuery,
    CreateBatchRequest,
    RemittanceRequest,
)
from backend.modules.settlement.service.batch_service import BatchService
from backend.modules.settlement.service.candidate_service import CandidateService
from backend.modules.settlement.service.document_reader import DocumentReader
from backend.tests.settlement.documents_support import complete_documents
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns

HK = "HONGKONG VISION DIGITAL PRINTING CO., LIMITED"


def services(engine):
    candidates = CandidateService(engine, fee_alert=Decimal("50"))
    return candidates, BatchService(engine, candidates, DocumentReader(), fee_alert=Decimal("50"))


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


def legacy_direct_batch(engine, number="REAL872", received="1000", fee="0"):
    """模拟 2026-11-18 之前已建的直接收汇批次：现在不能再通过接口新建，只保留结汇与作废。"""
    now = datetime(2026, 11, 10)
    with engine.begin() as connection:
        batch_id = batch_dao.insert_batch(
            connection,
            {
                "request_id": str(uuid.uuid4()),
                "route": "direct",
                "status": "collected",
                "consignee": "ACME LTD",
                "currency": "USD",
                "declared_total": Decimal("1000"),
                "received_on": date(2026, 11, 10),
                "received_amount": Decimal(received),
                "received_fee": Decimal(fee),
                "created_by": "finance-user",
            },
            now,
        )
        batch_dao.update_batch(connection, batch_id, {"batch_no": f"SB20261110-{batch_id:05d}"}, now)
        batch_item_dao.insert_items(
            connection,
            batch_id,
            [
                {
                    "declaration_no": number,
                    "consignee": "ACME LTD",
                    "currency": "USD",
                    "declared_amount": Decimal("1000"),
                }
            ],
            now,
        )
    return batch_id


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
    combined = candidates.query(CandidateQuery()).combinedTotals
    assert [(t.currency, t.count, t.amount) for t in combined] == [("USD", 3, "2000.50")]
    assert [(t.count, t.amount) for t in result.combinedTotals] == [(2, "1000.50")]


def test_candidates_mark_handling_and_summarise_by_consignee(seeded):
    candidates, batches = services(seeded)
    create(batches, ["REAL870"], "600")
    result = candidates.query(CandidateQuery())
    by_no = {item.declarationNo: item for item in result.items}
    # 沿用原有路径判定：香港中转建批次，直接收汇进总账
    assert (by_no["REAL870"].handling, by_no["REAL871"].handlingLabel) == ("batch", "登记回款建批次")
    assert (by_no["REAL872"].route, by_no["REAL872"].handling) == ("direct", "ledger")
    assert by_no["REAL872"].blockedReason == "" and by_no["REAL872"].handlingLabel == "进直接收汇明细"
    assert by_no["REAL870"].exportCompany == "申报主体" and by_no["REAL870"].exportDate == "2026-10-29"
    assert (result.total, result.truncated) == (3, False)
    # 全部报关单按路径汇总；未在批次中的另列
    assert {(t.route, t.amount) for t in result.totals} == {("hk_transit", "1000.50"), ("direct", "1000.00")}
    assert {(t.route, t.amount) for t in result.unsettled} == {
        ("hk_transit", "400.50"),
        ("direct", "1000.00"),
    }
    hk, direct = result.consignees
    assert (hk.consignee, hk.route, hk.count, hk.amount) == (HK, "hk_transit", 2, "1000.50")
    assert (hk.batchedCount, hk.pendingCount, hk.exportCompanies) == (1, 1, ["申报主体"])
    assert (hk.firstExportDate, hk.lastExportDate) == ("2026-10-29", "2026-10-29")
    assert (direct.consignee, direct.handling, direct.pendingCount) == ("ACME LTD", "ledger", 0)
    # 推荐组合只在香港中转的报关单中找
    note = candidates.query(CandidateQuery(consignee="ACME", targetAmount="1000")).suggestionNote
    assert note.startswith("请先按境外收货人筛选到同一家香港中转收货人")
    only = candidates.query(CandidateQuery(exportFrom="2026-10-30"))
    assert only.items == [] and only.consignees == []
    with pytest.raises(ValueError, match="出口日期开始不能晚于结束"):
        CandidateQuery(exportFrom="2026-11-02", exportTo="2026-11-01")


def test_hk_transit_batch_two_stage_reconciliation(seeded, tmp_path):
    candidates, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "985.50", fee="15.00", payer="Brazil Buyer")
    assert (batch.route, batch.status, batch.statusLabel) == ("hk_transit", "collected", "香港已收")
    assert batch.declaredTotal == "1000.50" and batch.balances[0].balanced
    assert batch.batchNo.startswith("SB") and [i.recordNo for i in batch.items] == ["CD870", "CD871"]
    # 金额已对平，但提单与销售合同未齐，不能确认资料已出
    assert not batch.actions.documentsReady.allowed and not batch.actions.settle.allowed
    assert batch.actions.documentsReady.reason.startswith("资料未齐")

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
    with pytest.raises(ApiError, match="资料未齐"):
        batches.documents_ready(batch.id, "finance-user")
    complete_documents(seeded, tmp_path, batch.id)
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


def test_direct_declarations_are_not_batched(seeded):
    _, batches = services(seeded)
    with pytest.raises(ApiError, match="直接收汇的报关单不建批次.*REAL872"):
        create(batches, ["REAL870", "REAL872"], "1600")
    with pytest.raises(ApiError, match="直接收汇的报关单不建批次"):
        create(batches, ["REAL872"], "1000")
    assert batches.browse(BatchQuery(status="all")).total == 0


def test_cancel_releases_declarations(seeded):
    _, batches = services(seeded)
    short = create(batches, ["REAL870"], "580", fee="10")
    assert short.route == "hk_transit" and not short.balances[0].balanced
    cancelled = batches.cancel(short.id, CancelRequest(reason="金额录错"), "finance-user")
    assert cancelled.status == "cancelled" and cancelled.cancelReason == "金额录错"
    again = create(batches, ["REAL870"], "590", fee="10")
    assert again.balances[0].balanced

    listing = batches.browse(BatchQuery(status="all", declarationNo="REAL870"))
    assert listing.total == 2
    assert {(c.route, c.status): c.count for c in listing.counts} == {
        ("hk_transit", "cancelled"): 1,
        ("hk_transit", "collected"): 1,
    }
    assert batches.browse(BatchQuery()).total == 1  # 默认只看未完结


def test_legacy_direct_batch_still_settles(seeded):
    _, batches = services(seeded)
    short = batches.get(legacy_direct_batch(seeded, received="980", fee="10"))
    assert short.route == "direct" and not short.balances[0].balanced
    assert short.actions.settle.reason == "到账加手续费与报关合计不一致，不能确认结汇"
    with pytest.raises(ApiError, match="不一致"):
        batches.settle(short.id, "finance-user")
    with pytest.raises(ApiError, match="仅香港中转"):
        batches.documents_ready(short.id, "finance-user")
    batches.cancel(short.id, CancelRequest(reason="金额录错"), "finance-user")
    again = legacy_direct_batch(seeded, received="990", fee="10")
    assert batches.settle(again, "finance-user").statusLabel == "已结汇"


def test_create_is_idempotent_and_service_identity_is_read_only(seeded):
    _, batches = services(seeded)
    body = CreateBatchRequest.model_validate(
        {
            "requestId": str(uuid.uuid4()),
            "declarationNos": ["REAL870"],
            "receivedOn": "2026-11-10",
            "receivedAmount": "600",
        }
    )
    first = batches.create(body, "finance-user")
    assert batches.create(body, "finance-user").id == first.id
    with pytest.raises(ApiError, match="服务身份只读"):
        batches.create(body, "service:robot")
    with pytest.raises(ValueError, match="最多两位小数"):
        CreateBatchRequest.model_validate({**body.model_dump(mode="json"), "receivedAmount": "1.005"})


def test_grouped_bank_amount_is_saved_and_balanced_as_decimal(seeded):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870", "REAL871"], "1,000.50")
    assert batch.receivedAmount == "1000.50"
    assert batch.declaredTotal == "1000.50"
    assert batch.balances[0].balanced
    assert batches.get(batch.id).receivedAmount == "1000.50"


def test_hk_registration_lists_only_unbatched_and_cancel_releases(seeded):
    candidates, batches = services(seeded)
    batch = create(batches, ["REAL870"], "600")
    query = CandidateQuery(route="hk_transit", batchStatus="unbatched", targetAmount="400.50")
    pending = candidates.query(query)
    assert [item.declarationNo for item in pending.items] == ["REAL871"]
    assert pending.suggestion == ["REAL871"]
    assert pending.combinedTotals[0].amount == "400.50"
    assert len(candidates.query(CandidateQuery()).items) == 3
    batches.cancel(batch.id, CancelRequest(reason="登记有误"), "finance-user")
    assert {item.declarationNo for item in candidates.query(query).items} == {"REAL870", "REAL871"}
    with pytest.raises(ValueError):
        CandidateQuery(batchStatus="unknown")
