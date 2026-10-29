"""matching 模块与整条链路：审核 → 任务 → 导入发票 → 比对建议 → 人工通过 → 任务完成；取消回退、驳回重生成、
硬性条件（币种待核实、红冲、容量、来源变化）、超开说明、重新审核延续进度、队列与摘要、HTTP。

来源经 source 真实保存，审核、任务、发票、比对均为真实服务（SQLite 隔离库，合成数据）。
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from backend.app import create_app, create_events
from backend.core.errors import ApiError
from backend.modules.invoice.dto.import_dto import ImportBody
from backend.modules.invoice.service.import_service import ImportService
from backend.modules.matching.dto.matching_dto import (
    BatchBody,
    CancelBody,
    CandidateQuery,
    ConfirmBody,
    GroupConfirmBody,
    GroupRejectBody,
    ManualBody,
    QueueQuery,
    RejectBody,
    SummaryBody,
)
from backend.modules.matching.service.allocation_service import AllocationService
from backend.modules.matching.service.matching_query_service import MatchingQueryService
from backend.modules.matching.service.proposal_service import ProposalService
from backend.modules.source.public import SourceDirectory
from backend.modules.task.service.task_service import TaskService
from backend.tests.documents_ready import complete_documents
from backend.tests.invoice_files import invoice, workbook
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from backend.tests.test_task import USER, approve
from fastapi.testclient import TestClient
from sqlalchemy import text

INK = ("墨水", "个", "10", "88.94", "11.56")  # 含税 100.50，与子采购行一致
FLUID = ("清洗液", "个", "10", "17.70", "2.30")  # 含税 20.00


@pytest.fixture
def world(engine):
    from backend.modules.source.public import DeclarationService
    from backend.tests.review_helpers import MaterializedReviewService as ReviewService

    events = create_events()
    queries = MatchingQueryService(engine)
    return {
        "review": ReviewService(engine, DeclarationService(engine), events),
        "imports": ImportService(engine, events),
        "queries": queries,
        "allocations": AllocationService(engine, events, queries),
        "proposals": ProposalService(engine),
        "tasks": TaskService(engine, SourceDirectory(engine)),
    }


def import_invoices(world, invoices, name="invoices.xlsx"):
    content = workbook(invoices)
    preview = world["imports"].process(ImportBody(filename=name, content=content), USER)
    body = ImportBody(filename=name, content=content, previewToken=preview.previewToken)
    return world["imports"].process(body, USER, commit=True)


def invoice_id(engine, number):
    return rows(engine, "SELECT id FROM invoice_headers WHERE invoice_no = :n", n=number)[0]["id"]


def task(engine):
    return rows(engine, "SELECT * FROM task_tasks WHERE status <> 'superseded' ORDER BY id")[-1]


@pytest.fixture
def reviewed(ns, engine, world):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")
    return task(engine)


def proposals(world, number_id):
    view = world["queries"].invoice(number_id)
    return [
        allocation
        for item in view.items
        for allocation in item.allocations
        if allocation.status == "proposed"
    ]


def group(world, number_id):
    """该发票唯一一组待审核整单建议。"""
    (found,) = world["queries"].invoice(number_id).groups
    return found


def confirm_group(world, number_id, note=""):
    body = GroupConfirmBody(invoiceId=str(number_id), note=note)
    return world["allocations"].confirm_group(group(world, number_id).id, body, USER)


def manual(world, engine, number_id, line_index, item_index=0, *, quantity="10", amount, note="人工核对"):
    view = world["queries"].invoice(number_id)
    line = rows(engine, "SELECT id FROM source_purchase_order_lines ORDER BY id")[line_index]["id"]
    body = ManualBody(
        requestId=uuid4(),
        invoiceId=str(number_id),
        invoiceItemId=view.items[item_index].id,
        purchaseLineId=str(line),
        quantity=quantity,
        amount=amount,
        note=note,
    )
    return world["allocations"].create_manual(body, USER), body


def test_queue_counts_with_all_confidence_tiers(engine, world, reviewed):
    assert world["queries"].queue(QueueQuery()).counts == {
        "all": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
    }
    import_invoices(
        world,
        [
            invoice("26000000000000008901", [INK, FLUID], remark="SUB-200"),
            # 备注未写单号、销售方名称相近：按供应商模糊召回整单，中置信度
            invoice("26000000000000008902", [INK, FLUID], seller="上海供货商有限公司"),
            invoice("26000000000000008903", [("其他商品", "箱", "1000", "100000", "0")]),
        ],
    )
    # 整单建议几乎不会是低置信度；模拟一条低置信建议以覆盖三档非空时的计数类型
    with engine.begin() as connection:
        lowest = connection.execute(
            text("SELECT MAX(id) FROM matching_allocations WHERE status = 'proposed'")
        ).scalar()
        connection.execute(
            text("UPDATE matching_allocations SET confidence = 40 WHERE id = :i"), {"i": lowest}
        )
    expected = {"all": 4, "high": 2, "medium": 1, "low": 1}
    for tier, total in expected.items():
        result = world["queries"].queue(QueueQuery(tier=tier, pageSize=1))
        assert result.total == total and len(result.rows) == 1
        assert result.pages == total and result.counts == expected
        assert all(type(value) is int for value in result.counts.values())


def test_full_chain_from_review_to_completed_task(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008001", [INK, FLUID], remark="请款 SUB-200")])
    target = invoice_id(engine, "26000000000000008001")
    found = group(world, target)
    # 整单合计：订单、供应商、品名、单位、数量、金额、税额一致；购买方未提供只扣分不要求说明
    assert (found.tier, found.confidence, found.noteReasons) == ("high", "95", [])
    assert found.confirm.allowed and [order.orderNo for order in found.orders] == ["SUB-200"]
    assert {check.key: check.result for check in found.items[0].checks}["tax"] == "match"
    assert len(proposals(world, target)) == 2
    # 整单建议不能逐条通过或驳回
    with pytest.raises(ApiError, match="整组"):
        world["allocations"].confirm(int(found.allocationIds[0]), ConfirmBody(), USER)
    with pytest.raises(ApiError, match="整组"):
        world["allocations"].reject(int(found.allocationIds[0]), RejectBody(), USER)
    view = confirm_group(world, target)
    assert view.groups == []
    assert all(a.status == "confirmed" for item in view.items for a in item.allocations)
    waiting = task(engine)
    # 发票已收齐但资料未到齐：停在"资料待补齐"，完成节点写明尚缺的资料
    assert waiting["status"] == "documents_incomplete" and waiting["completed_at"] is None
    steps = world["tasks"].detail(waiting["id"]).steps
    assert [step.state for step in steps] == ["done", "current", "waiting", "done", "done", "waiting"]
    assert "子采购合同" in steps[-1].description and "回签合同" in steps[-1].description
    complete_documents(engine)
    done = task(engine)
    assert done["status"] == "completed" and done["completed_at"] is not None
    lines = rows(engine, "SELECT status, received_amount FROM task_lines ORDER BY purchase_line_id")
    assert [(r["status"], Decimal(str(r["received_amount"]))) for r in lines] == [
        ("received", Decimal("100.5")),
        ("received", Decimal("20")),
    ]
    events = [e["to_status"] for e in rows(engine, "SELECT to_status FROM task_events ORDER BY id")]
    assert events[0] == "documents_pending" and events[-2:] == ["documents_incomplete", "completed"]
    summary = world["queries"].summaries(SummaryBody(invoiceIds=[str(target)])).rows[0]
    assert (summary.status, summary.confirmed) == ("confirmed", 2)


def test_cancel_rolls_task_back_to_actual_progress(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008002", [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008002")
    first, second = proposals(world, target)
    confirm_group(world, target)
    world["allocations"].cancel(int(first.id), CancelBody(reason="发票录错"), USER)
    assert task(engine)["status"] == "partially_received"
    world["allocations"].cancel(int(second.id), CancelBody(reason="发票录错"), USER)
    assert task(engine)["status"] == "documents_pending"
    assert {r["status"] for r in rows(engine, "SELECT status FROM task_lines")} == {"open"}
    assert world["proposals"].generate_now([target], USER) == 2
    with pytest.raises(ApiError, match="只有已通过"):
        world["allocations"].cancel(int(proposals(world, target)[0].id), CancelBody(reason="x"), USER)


def test_reject_and_regenerate(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008003", [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008003")
    found = group(world, target)
    body = GroupRejectBody(invoiceId=str(target), note="品名待核")
    view = world["allocations"].reject_group(found.id, body, USER)
    assert view.groups == [] and proposals(world, target) == []
    assert world["proposals"].generate_now([target], USER) == 2
    assert len(proposals(world, target)) == 2


def test_partial_invoice_gets_no_proposal_and_uses_manual(engine, world, reviewed):
    # 只开了子采购单的一部分：不自动建议，人工关联作为例外入口
    import_invoices(world, [invoice("26000000000000008012", [INK], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008012")
    assert proposals(world, target) == [] and world["queries"].invoice(target).groups == []
    view, _ = manual(world, engine, target, 0, amount="100.50")
    assert [a.status for a in view.items[0].allocations] == ["confirmed"]
    assert task(engine)["status"] == "partially_received"


def test_supplier_difference_requires_note_and_overinvoice_is_flagged(engine, world, reviewed):
    import_invoices(
        world,
        [invoice("26000000000000008004", [INK, FLUID], remark="SUB-200", seller="上海供货商有限公司")],
    )
    target = invoice_id(engine, "26000000000000008004")
    found = group(world, target)
    assert found.tier == "high" and "销售方与供应商不一致" in found.noteReasons
    with pytest.raises(ApiError, match="请填写审核说明") as error:
        confirm_group(world, target)
    assert error.value.status == 400
    confirm_group(world, target, note="开票名称与 NS 供应商为同一主体")
    notes = {row["review_note"] for row in rows(engine, "SELECT review_note FROM matching_allocations")}
    assert notes == {"开票名称与 NS 供应商为同一主体"}
    # 超开只能人工关联，须填写说明并标记
    over = ("墨水", "个", "12", "106.73", "13.87")  # 含税 120.60，超过应开
    import_invoices(world, [invoice("26000000000000008013", [over], remark="SUB-200")], "o.xlsx")
    extra = invoice_id(engine, "26000000000000008013")
    assert proposals(world, extra) == []
    manual(world, engine, extra, 0, quantity="2", amount="20.10", note="供应商多开两件，已确认")
    saved = rows(engine, "SELECT exceeds_expected FROM matching_allocations WHERE invoice_id = :i", i=extra)
    assert saved[0]["exceeds_expected"]


def test_unresolved_currency_and_red_offset_block(ns, engine, world):
    save(ns, engine, bundle([purchase()], [customs("870")], parents={}))
    approve(world, "CD870")
    import_invoices(world, [invoice("26000000000000008005", [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008005")
    # 子采购币种待核实的整单不会被建议，人工关联同样被拒绝
    assert proposals(world, target) == []
    with pytest.raises(ApiError, match="币种待核实"):
        manual(world, engine, target, 0, amount="100.50")
    import_invoices(
        world, [invoice("26000000000000008006", [INK, FLUID], remark="SUB-200", status="已红冲")], "r.xlsx"
    )
    assert proposals(world, invoice_id(engine, "26000000000000008006")) == []


def test_capacity_and_stale_source_block(ns, engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008007", [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008007")
    group(world, target)
    # 同票墨水行先人工分出一部分：整单再通过会超过发票行本身
    manual(world, engine, target, 1, quantity="1", amount="20.00", note="同票部分分给清洗液")
    blocked = group(world, target)
    assert not blocked.confirm.allowed and "超过发票行本身" in blocked.confirm.reason
    with pytest.raises(ApiError, match="超过发票行本身"):
        confirm_group(world, target, note="x")
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    view = world["queries"].invoice(target)
    stale = [a for item in view.items for a in item.allocations if a.status == "rejected"]
    assert stale and all(not a.confirm.allowed and "变化" in a.reviewNote for a in stale)


def test_manual_allocation_is_idempotent(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008008", [FLUID], remark="")])
    target = invoice_id(engine, "26000000000000008008")
    item = world["queries"].invoice(target).items[0]
    assert proposals(world, target) == []  # 只开清洗液，不是整张子采购单
    candidates = world["queries"].candidates(
        CandidateQuery(invoiceId=str(target), invoiceItemId=item.id, keyword="清洗")
    )
    assert candidates.total == 1 and candidates.rows[0].block == ""
    body = ManualBody(
        requestId=uuid4(),
        invoiceId=str(target),
        invoiceItemId=item.id,
        purchaseLineId=candidates.rows[0].purchase.purchaseLineId,
        quantity="10",
        amount="20.00",
        note="备注未写子采购单号，人工核对",
    )
    world["allocations"].create_manual(body, USER)
    world["allocations"].create_manual(body, USER)
    with pytest.raises(ApiError, match="已有有效记录") as error:
        world["allocations"].create_manual(body.model_copy(update={"requestId": uuid4()}), USER)
    assert error.value.status == 409
    confirmed = rows(engine, "SELECT confidence, status FROM matching_allocations WHERE status = 'confirmed'")
    assert len(confirmed) == 1 and confirmed[0]["confidence"] is None


def test_reapproval_carries_received_progress(ns, engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008009", [INK], remark="SUB-200")])
    manual(world, engine, invoice_id(engine, "26000000000000008009"), 0, amount="100.50")
    save(ns, engine, bundle([purchase(amounts=("100.50", "25.00"))], [customs("870")]))
    approve(world, "CD870")
    current = task(engine)
    assert current["review_revision"] == 2 and current["status"] == "partially_received"
    line = rows(
        engine, "SELECT * FROM task_lines WHERE task_id = :t ORDER BY purchase_line_id", t=current["id"]
    )[0]
    assert line["status"] == "received" and Decimal(str(line["received_amount"])) == Decimal("100.5")


def test_queue_batch_and_service_identity(engine, world, reviewed):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    import_invoices(world, [invoice("26000000000000008010", [INK, FLUID], remark="SUB-200")])
    queue = world["queries"].queue(QueueQuery(tier="high"))
    assert queue.total == 2 and queue.counts["high"] == 2
    with pytest.raises(ApiError) as error:
        world["allocations"].confirm(int(queue.rows[0].allocation.id), ConfirmBody(), "service:bot")
    assert error.value.status == 403
    result = world["allocations"].confirm_batch(
        BatchBody(ids=[row.allocation.id for row in queue.rows]), USER
    )
    assert result == {"confirmed": 2, "skipped": []} and task(engine)["status"] == "completed"


def test_http_matching_routes(context, ns, engine):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    app = create_app(context.settings, context.ns, engine)
    app.state.review_calculations.rebuild()
    with TestClient(app) as client:
        assert client.post("/api/matching/queue", json={}).status_code == 401
        assert client.post("/api/matching/invoice-queue/query", json={}).status_code == 401
        headers = {"Origin": context.settings.origin}
        login = client.post(
            "/api/session",
            headers=headers,
            json={"username": "admin", "password": context.settings.admin_password},
        )
        assert login.status_code == 200
        item = client.post("/api/review/declarations/query", json={}, headers=headers).json()["groups"][0]
        client.post(
            f"/api/review/declarations/{item['id']}/approve",
            json={"contentSha256": item["contentSha256"]},
            headers=headers,
        )
        complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
        content = workbook([invoice("26000000000000008011", [INK, FLUID], remark="SUB-200")])
        body = {"filename": "i.xlsx", "content": content}
        token = client.post("/api/invoices/import/preview", json=body, headers=headers).json()["previewToken"]
        client.post("/api/invoices/import/confirm", json={**body, "previewToken": token}, headers=headers)
        queue = client.post("/api/matching/queue", json={"tier": "high"}, headers=headers).json()
        assert queue["total"] == 2
        grouped = client.post("/api/matching/invoice-queue/query", json={}, headers=headers)
        assert grouped.status_code == 200
        assert grouped.json()["total"] == 1 and grouped.json()["rows"][0]["proposalCount"] == 2
        ids = [row["allocation"]["id"] for row in queue["rows"]]
        batch = client.post("/api/matching/allocations/confirm-batch", json={"ids": ids}, headers=headers)
        assert batch.status_code == 200 and batch.json()["confirmed"] == 2
        task_id = client.post("/api/tasks/query", json={}, headers=headers).json()["groups"][0]["tasks"][0][
            "id"
        ]
        assert client.get(f"/api/tasks/{task_id}", headers=headers).json()["task"]["status"] == "completed"
        bad = client.post("/api/matching/allocations", json={"requestId": "x"}, headers=headers)
        assert bad.status_code == 400
