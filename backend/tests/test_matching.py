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
from backend.tests.invoice_files import invoice, workbook
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from backend.tests.test_task import USER, approve
from fastapi.testclient import TestClient

INK = ("墨水", "个", "10", "88.94", "11.56")  # 含税 100.50，与子采购行一致
FLUID = ("清洗液", "个", "10", "17.70", "2.30")  # 含税 20.00


@pytest.fixture
def world(engine):
    from backend.modules.review.service.review_service import ReviewService
    from backend.modules.source.public import DeclarationService

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
            invoice("26000000000000008902", [INK]),
            invoice("26000000000000008903", [("其他商品", "箱", "1000", "100000", "0")]),
        ],
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
    found = proposals(world, target)
    assert len(found) == 2 and all(p.tier == "high" and p.confidence == "90" for p in found)
    assert all(p.confirm.allowed and p.noteReasons == [] for p in found)  # 购买方未提供不要求说明
    first, second = found
    world["allocations"].confirm(int(first.id), ConfirmBody(), USER)
    assert task(engine)["status"] == "partially_received"
    view = world["allocations"].confirm(int(second.id), ConfirmBody(), USER)
    assert all(a.status == "confirmed" for item in view.items for a in item.allocations)
    done = task(engine)
    assert done["status"] == "completed" and done["completed_at"] is not None
    # 发票先于合同与通知到达：节点按各自事实显示，不因任务完成而标记合同、通知已完成。
    steps = world["tasks"].detail(done["id"]).steps
    assert [step.state for step in steps] == ["done", "waiting", "waiting", "done", "done", "done"]
    lines = rows(engine, "SELECT status, received_amount FROM task_lines ORDER BY purchase_line_id")
    assert [(r["status"], Decimal(str(r["received_amount"]))) for r in lines] == [
        ("received", Decimal("100.5")),
        ("received", Decimal("20")),
    ]
    events = [e["to_status"] for e in rows(engine, "SELECT to_status FROM task_events ORDER BY id")]
    assert events == ["documents_pending", "partially_received", "completed"]
    summary = world["queries"].summaries(SummaryBody(invoiceIds=[str(target)])).rows[0]
    assert (summary.status, summary.confirmed) == ("confirmed", 2)


def test_cancel_rolls_task_back_to_actual_progress(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008002", [INK, FLUID], remark="SUB-200")])
    first, second = proposals(world, invoice_id(engine, "26000000000000008002"))
    for proposal in (first, second):
        world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)
    world["allocations"].cancel(int(first.id), CancelBody(reason="发票录错"), USER)
    assert task(engine)["status"] == "partially_received"
    world["allocations"].cancel(int(second.id), CancelBody(reason="发票录错"), USER)
    assert task(engine)["status"] == "documents_pending"
    assert {r["status"] for r in rows(engine, "SELECT status FROM task_lines")} == {"open"}
    target = invoice_id(engine, "26000000000000008002")
    assert world["proposals"].generate_now([target], USER) == 2
    with pytest.raises(ApiError, match="只有已通过"):
        world["allocations"].cancel(int(proposals(world, target)[0].id), CancelBody(reason="x"), USER)


def test_reject_and_regenerate(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008003", [INK], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008003")
    (proposal,) = proposals(world, target)
    world["allocations"].reject(int(proposal.id), RejectBody(note="品名待核"), USER)
    assert proposals(world, target) == []
    assert world["proposals"].generate_now([target], USER) == 1
    assert len(proposals(world, target)) == 1


def test_inconsistent_items_require_note_and_overinvoice_is_flagged(engine, world, reviewed):
    over = ("墨水", "个", "12", "106.73", "13.87")  # 含税 120.60，超过应开 100.50
    import_invoices(world, [invoice("26000000000000008004", [over], remark="SUB-200")])
    (proposal,) = proposals(world, invoice_id(engine, "26000000000000008004"))
    assert proposal.tier == "medium" and "数量不一致" in proposal.noteReasons
    with pytest.raises(ApiError, match="请填写审核说明") as error:
        world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)
    assert error.value.status == 400
    world["allocations"].confirm(int(proposal.id), ConfirmBody(note="供应商多开两件，已确认"), USER)
    saved = rows(engine, "SELECT exceeds_expected, review_note FROM matching_allocations")[0]
    assert saved["exceeds_expected"] and saved["review_note"] == "供应商多开两件，已确认"
    line = rows(engine, "SELECT * FROM task_lines ORDER BY purchase_line_id")[0]
    assert line["status"] == "partial" and line["over_invoiced"]


def test_unresolved_currency_and_red_offset_block(ns, engine, world):
    save(ns, engine, bundle([purchase()], [customs("870")], parents={}))
    approve(world, "CD870")
    import_invoices(world, [invoice("26000000000000008005", [INK], remark="SUB-200")])
    (proposal,) = proposals(world, invoice_id(engine, "26000000000000008005"))
    assert not proposal.confirm.allowed and "币种待核实" in proposal.confirm.reason
    with pytest.raises(ApiError, match="币种待核实"):
        world["allocations"].confirm(int(proposal.id), ConfirmBody(note="x"), USER)
    import_invoices(
        world, [invoice("26000000000000008006", [INK], remark="SUB-200", status="已红冲")], "r.xlsx"
    )
    assert proposals(world, invoice_id(engine, "26000000000000008006")) == []


def test_capacity_and_stale_source_block(ns, engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008007", [INK], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008007")
    (proposal,) = proposals(world, target)
    item_id = proposal.invoiceItemId
    fluid_line = rows(engine, "SELECT id FROM source_purchase_order_lines ORDER BY id")[1]["id"]
    manual = ManualBody(
        requestId=uuid4(),
        invoiceId=str(target),
        invoiceItemId=item_id,
        purchaseLineId=str(fluid_line),
        quantity="1",
        amount="20.00",
        note="同票部分分给清洗液",
    )
    world["allocations"].create_manual(manual, USER)
    with pytest.raises(ApiError, match="超过发票行本身"):
        world["allocations"].confirm(int(proposal.id), ConfirmBody(note="x"), USER)
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    stale = next(a for a in world["queries"].invoice(target).items[0].allocations if a.status == "rejected")
    assert not stale.confirm.allowed
    assert "变化" in stale.reviewNote


def test_manual_allocation_is_idempotent(engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008008", [FLUID], remark="")])
    target = invoice_id(engine, "26000000000000008008")
    item = world["queries"].invoice(target).items[0]
    (proposal,) = [a for a in item.allocations if a.status == "proposed"]  # 销售方名称召回的建议
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
    with pytest.raises(ApiError, match="已有有效记录") as error:
        world["allocations"].create_manual(body, USER)
    assert error.value.status == 409
    world["allocations"].reject(int(proposal.id), RejectBody(), USER)
    world["allocations"].create_manual(body, USER)
    world["allocations"].create_manual(body, USER)
    confirmed = rows(engine, "SELECT confidence, status FROM matching_allocations WHERE status = 'confirmed'")
    assert len(confirmed) == 1 and confirmed[0]["confidence"] is None


def test_reapproval_carries_received_progress(ns, engine, world, reviewed):
    import_invoices(world, [invoice("26000000000000008009", [INK], remark="SUB-200")])
    (proposal,) = proposals(world, invoice_id(engine, "26000000000000008009"))
    world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)
    save(ns, engine, bundle([purchase(amounts=("100.50", "25.00"))], [customs("870")]))
    approve(world, "CD870")
    current = task(engine)
    assert current["review_revision"] == 2 and current["status"] == "partially_received"
    line = rows(
        engine, "SELECT * FROM task_lines WHERE task_id = :t ORDER BY purchase_line_id", t=current["id"]
    )[0]
    assert line["status"] == "received" and Decimal(str(line["received_amount"])) == Decimal("100.5")


def test_queue_batch_and_service_identity(engine, world, reviewed):
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
    with TestClient(app) as client:
        assert client.post("/api/matching/queue", json={}).status_code == 401
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
        content = workbook([invoice("26000000000000008011", [INK, FLUID], remark="SUB-200")])
        body = {"filename": "i.xlsx", "content": content}
        token = client.post("/api/invoices/import/preview", json=body, headers=headers).json()["previewToken"]
        client.post("/api/invoices/import/confirm", json={**body, "previewToken": token}, headers=headers)
        queue = client.post("/api/matching/queue", json={"tier": "high"}, headers=headers).json()
        assert queue["total"] == 2
        ids = [row["allocation"]["id"] for row in queue["rows"]]
        batch = client.post("/api/matching/allocations/confirm-batch", json={"ids": ids}, headers=headers)
        assert batch.status_code == 200 and batch.json()["confirmed"] == 2
        task_id = client.post("/api/tasks/query", json={}, headers=headers).json()["groups"][0]["tasks"][0][
            "id"
        ]
        assert client.get(f"/api/tasks/{task_id}", headers=headers).json()["task"]["status"] == "completed"
        bad = client.post("/api/matching/allocations", json={"requestId": "x"}, headers=headers)
        assert bad.status_code == 400
