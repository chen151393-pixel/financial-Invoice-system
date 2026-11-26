"""双审核门槛、版本、权限、异常人工确认、幂等、回滚与可选 MySQL 并发。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from backend.app import create_events
from backend.core.errors import ApiError
from backend.modules.review.dto.customs_receipt_dto import CustomsApproveRequest, CustomsReceiptQuery
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.public import InvoiceReady
from backend.modules.review.service.calculation_service import CalculationService
from backend.modules.review.service.customs_approval_service import CustomsApprovalService
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService
from backend.modules.task.dao.supplier_setting_dao import insert_setting
from backend.modules.task.public import review_task_outcomes
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import text

USER = "user:admin"


@pytest.fixture
def world(schema_engine, ns):
    engine = schema_engine
    events = create_events()
    save(ns, engine, bundle([purchase()], [customs("870")]))
    receipts = CustomsReceiptService(engine, task_reader=review_task_outcomes)
    # 与来源报关行一一对应，数量 10 个、总价 USD 15 均一致，可自动审核
    _import(
        receipts,
        [
            row("REAL870", "01", "墨水", "个", 10, total=15),
            row("REAL870", "02", "清洗液", "个", 10, total=15),
        ],
    )
    review = ReviewService(engine, DeclarationService(engine), events, task_reader=review_task_outcomes)
    return engine, events, receipts, review


def body(receipt, method="auto", note=""):
    return CustomsApproveRequest(
        items=[{"id": receipt.id, "token": receipt.approval.token}], method=method, note=note
    )


def current(world):
    return world[2].browse(CustomsReceiptQuery()).items[0]


def finance(world):
    engine, _, _, review = world
    declaration = rows(engine, "SELECT id, content_sha256 FROM source_customs_declarations")[0]
    review.approve(declaration["id"], ApproveRequest(contentSha256=declaration["content_sha256"]), USER)


def progress_on_both_pages(world):
    review = world[3]
    CalculationService(review).rebuild()
    groups = review.browse(DeclarationListQuery(exactDeclarationNo="REAL870")).groups
    receipts = world[2].browse(CustomsReceiptQuery(exactDeclarationNo="REAL870")).items
    assert len(groups) == len(receipts) == 1
    progress = groups[0].approvalProgress
    assert progress is not None and progress.linked
    assert progress == receipts[0].approvalProgress
    return progress


def approve(world, request):
    return CustomsApprovalService(world[0], world[1]).approve_batch(request, USER)


def test_finance_list_filters_current_customs_approval_independently(world):
    engine, _, _, review = world
    CalculationService(review).rebuild()
    query = DeclarationListQuery(status="customs_approved", pageSize=1)
    assert review.browse(query).counts["customsApproved"] == 0
    assert review.browse(query).total == 0
    approve(world, body(current(world)))
    result = review.browse(query)
    assert result.total == result.counts["customsApproved"] == 1
    assert len(result.groups) == 1
    assert result.groups[0].approvalProgress.customs.status == "approved"
    assert result.groups[0].review.status == "pending"
    assert review.browse(DeclarationListQuery(status="customs_approved", page=2, pageSize=1)).groups == []
    missing = review.browse(DeclarationListQuery(status="customs_approved", recordNo="不存在"))
    assert missing.total == missing.counts["customsApproved"] == 0
    finance(world)
    CalculationService(review).rebuild()
    assert review.browse(query).total == 1
    # 当前 NS 摘要变化后，即使财务快照尚未重建，也不能沿用历史海关通过记录。
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE source_customs_declarations SET content_sha256=:digest"), {"digest": "a" * 64}
        )
    assert review.browse(query).total == 0


def test_finance_list_excludes_replaced_receipt_approval(world):
    engine, _, _, review = world
    CalculationService(review).rebuild()
    approve(world, body(current(world)))
    query = DeclarationListQuery(status="customs_approved")
    assert review.browse(query).total == 1
    with engine.begin() as connection:
        connection.execute(text("UPDATE review_customs_receipts SET revision=revision+1"))
    assert review.browse(query).total == 0


def test_finance_list_excludes_duplicate_customs_number(world, ns):
    engine, _, _, review = world
    CalculationService(review).rebuild()
    approve(world, body(current(world)))
    duplicate = customs("871")
    duplicate[1]["custrecord_swc_realno"] = "REAL870"
    save(ns, engine, bundle([purchase("201", "871")], [duplicate]))
    result = review.browse(DeclarationListQuery(status="customs_approved"))
    assert result.total == result.counts["customsApproved"] == 0


@pytest.mark.parametrize("first", ["finance", "customs"])
def test_both_orders_release_once_and_audit(world, first):
    request = body(current(world))
    actions = {"finance": lambda: finance(world), "customs": lambda: approve(world, request)}
    actions[first]()
    assert rows(world[0], "SELECT * FROM task_tasks") == []
    pending = progress_on_both_pages(world)
    assert pending.status == ("waiting_customs" if first == "finance" else "waiting_finance")
    assert pending.taskIds == []
    actions["customs" if first == "finance" else "finance"]()
    assert len(rows(world[0], "SELECT * FROM task_tasks")) == 1
    assert len(rows(world[0], "SELECT * FROM task_lines")) == 2
    released = progress_on_both_pages(world)
    assert released.status == "created"
    assert released.finance.status == released.customs.status == "approved"
    assert released.taskIds == [str(rows(world[0], "SELECT id FROM task_tasks")[0]["id"])]
    assert len(approve(world, request).approved) == 1
    finance(world)
    assert len(rows(world[0], "SELECT * FROM review_records WHERE customs_approval_id IS NOT NULL")) == 1
    assert len(rows(world[0], "SELECT * FROM review_customs_approvals")) == 1
    assert current(world).approval.label == "自动审核通过"


def test_progress_explains_current_supplier_settings_when_no_task_exists(world):
    supplier = rows(world[0], "SELECT id FROM source_suppliers")[0]
    with world[0].begin() as connection:
        insert_setting(connection, supplier["id"], False, USER, datetime.now(UTC).replace(tzinfo=None))
    finance(world)
    approve(world, body(current(world)))
    progress = progress_on_both_pages(world)
    assert progress.finance.status == progress.customs.status == "approved"
    assert progress.status == "no_task" and progress.taskIds == []
    assert "供应商当前已关闭通知" in progress.reason


def test_exact_cross_page_queries_do_not_match_similar_numbers(world):
    review = world[3]
    CalculationService(review).rebuild()
    assert review.browse(DeclarationListQuery(declarationNo="REAL87")).total == 1
    assert review.browse(DeclarationListQuery(exactDeclarationNo="REAL87")).total == 0
    assert world[2].browse(CustomsReceiptQuery(declarationNo="REAL87")).total == 1
    assert world[2].browse(CustomsReceiptQuery(exactDeclarationNo="REAL87")).total == 0


def test_auto_rejects_differences_manual_note_optional_and_audited(world):
    _import(world[2], [row("REAL870", "01", "墨水", "个", 9), row("REAL870", "02", "清洗液", "个", 10)])
    item = current(world)
    assert item.approval.allowed and not item.approval.autoAllowed
    assert "仅逐行一一对应" in approve(world, body(item)).skipped[0].reason
    # 差异单人工审核不强制说明，审核人、方式与时间照常留痕
    assert approve(world, body(item, "manual")).approved
    approved = current(world).approval
    assert (approved.label, approved.approvedBy, approved.note) == ("人工审核通过", USER, "")
    assert approved.approvedAt
    audit = rows(world[0], "SELECT method, approved_by, note FROM review_customs_approvals")
    assert [(r["method"], r["approved_by"], r["note"]) for r in audit] == [("manual", USER, None)]


@pytest.mark.parametrize(
    ("rows_", "reason"),
    [
        # 拆行：NS 1 行对应海关 2 项
        (
            [
                row("REAL870", "01", "墨水", "个", 6, total=9),
                row("REAL870", "02", "墨水", "个", 4, total=6),
                row("REAL870", "03", "清洗液", "个", 10, total=15),
            ],
            "拆行或合并",
        ),
        # 数量一致、总价不一致
        (
            [
                row("REAL870", "01", "墨水", "个", 10, total=15),
                row("REAL870", "02", "清洗液", "个", 10, total=16),
            ],
            "有差异",
        ),
    ],
)
def test_split_rows_and_total_mismatch_go_to_manual_review(world, rows_, reason):
    _import(world[2], rows_)
    item = current(world)
    assert item.approval.allowed and not item.approval.autoAllowed and reason in item.approval.reason
    skipped = approve(world, body(item)).skipped[0].reason
    assert "仅逐行一一对应" in skipped and reason in skipped
    assert approve(world, body(item, "manual", "已人工核实")).approved
    assert current(world).approval.label == "人工审核通过"
    assert current(world).approval.note == "已人工核实"


def test_stale_source_and_reimport_invalidate_approval(world, ns):
    original = current(world)
    approve(world, body(original))
    assert world[2].browse(CustomsReceiptQuery(status="approved")).counts.approved == 1
    save(ns, world[0], bundle([purchase(amounts=("130", "20"))], [customs("870", "2026-09-03T10:00:00Z")]))
    assert not current(world).approval.approved
    stale = world[2].browse(CustomsReceiptQuery(status="approved"))
    assert stale.counts.approved == stale.total == 0 and stale.items == []
    assert current(world).approvalProgress.customs.status == "changed"
    assert "已变化" in approve(world, body(original)).skipped[0].reason
    finance(world)
    assert rows(world[0], "SELECT * FROM task_tasks") == []
    request = body(current(world))
    _import(
        world[2],
        [
            row("REAL870", "01", "墨水", "个", 10, "NEW", total=15),
            row("REAL870", "02", "清洗液", "个", 10, "NEW", total=15),
        ],
    )
    assert "已变化" in approve(world, request).skipped[0].reason
    assert not current(world).approval.approved
    assert world[2].browse(CustomsReceiptQuery(status="approved")).counts.approved == 0
    assert approve(world, body(current(world))).approved
    assert world[2].browse(CustomsReceiptQuery(status="approved")).total == 1
    assert len(rows(world[0], "SELECT * FROM task_tasks")) == 1


@pytest.mark.parametrize("method", ["auto", "manual"])
def test_approved_filter_counts_only_current_approvals(world, method):
    before = world[2].browse(CustomsReceiptQuery(status="approved"))
    assert before.counts.receipts == before.counts.matched == 1
    assert before.counts.approved == before.total == 0 and before.items == []
    assert approve(world, body(current(world), method)).approved
    approved = world[2].browse(CustomsReceiptQuery(status="approved"))
    assert approved.counts.approved == approved.total == 1
    assert approved.items[0].approval.approved
    # 海关审核独立统计，不要求财务通过；原比对分类继续包含该回执。
    assert approved.items[0].approvalProgress.finance.status != "approved"
    assert world[2].browse(CustomsReceiptQuery(status="matched")).total == 1
    assert world[2].browse(CustomsReceiptQuery()).counts.approved == 1


def test_approved_filter_search_difference_and_database_pagination(world, ns):
    save(
        ns,
        world[0],
        bundle(
            [purchase("201", "871"), purchase("202", "872")],
            [customs("871"), customs("872")],
        ),
    )
    _import(
        world[2],
        [
            row("REAL871", "01", "墨水", "个", 10, "客户乙", total=16),
            row("REAL871", "02", "清洗液", "个", 10, "客户乙", total=15),
            row("REAL872", "01", "相纸", "个", 1, "待审核客户", total=15),
            row("MISSING", "01", "相纸", "个", 1, total=15),
        ],
    )
    for number in ("REAL870", "REAL871"):
        item = world[2].browse(CustomsReceiptQuery(exactDeclarationNo=number)).items[0]
        assert approve(world, body(item, "manual")).approved
    first = world[2].browse(CustomsReceiptQuery(status="approved", pageSize=1))
    second = world[2].browse(CustomsReceiptQuery(status="approved", pageSize=1, page=2))
    assert first.total == second.total == first.counts.approved == 2
    assert first.counts.receipts == 4 and first.pages == second.pages == 2
    assert [item.declarationNo for item in first.items + second.items] == ["REAL871", "REAL870"]
    assert all(item.approval.approved for item in first.items + second.items)
    narrowed = world[2].browse(
        CustomsReceiptQuery(
            status="approved", name="墨水", consignee="客户乙", exportFrom="2026-10-29", exportTo="2026-10-29"
        )
    )
    assert narrowed.total == narrowed.counts.approved == 1
    assert narrowed.items[0].declarationNo == "REAL871"
    different = world[2].browse(CustomsReceiptQuery(status="approved", difference="total_mismatch"))
    assert different.total == 1 and different.items[0].declarationNo == "REAL871"
    assert different.counts.approved == 2
    assert world[2].browse(CustomsReceiptQuery(status="approved", difference="unit_mismatch")).total == 0
    absent = world[2].browse(CustomsReceiptQuery(status="approved", declarationNo="MISSING"))
    assert absent.counts.receipts == 1 and absent.counts.approved == absent.total == 0
    assert world[2].browse(CustomsReceiptQuery(status="approved", page=3, pageSize=1)).items == []


def test_approved_filter_excludes_new_duplicate_ns_number(world, ns):
    assert approve(world, body(current(world))).approved
    duplicate = customs("871")
    duplicate[1]["custrecord_swc_realno"] = "REAL870"
    save(ns, world[0], bundle([purchase("201", "871")], [duplicate]))
    result = world[2].browse(CustomsReceiptQuery(status="approved"))
    assert result.total == result.counts.approved == 0 and result.items == []


def test_approved_filter_excludes_changed_receipt_version(world):
    assert approve(world, body(current(world))).approved
    _import(
        world[2],
        [
            row("REAL870", "01", "墨水", "个", 10, "新客户", total=15),
            row("REAL870", "02", "清洗液", "个", 10, "新客户", total=15),
        ],
    )
    result = world[2].browse(CustomsReceiptQuery(status="approved"))
    assert result.counts.receipts == result.counts.matched == 1
    assert result.total == result.counts.approved == 0 and result.items == []
    assert approve(world, body(current(world))).approved
    result = world[2].browse(CustomsReceiptQuery(status="approved"))
    assert result.total == result.counts.approved == 1


def test_partial_results_missing_ns_and_identity(world):
    _import(world[2], [row("MISSING", "01", "相纸", "千克", 1)])
    items = world[2].browse(CustomsReceiptQuery()).items
    request = CustomsApproveRequest(items=[{"id": item.id, "token": item.approval.token} for item in items])
    result = approve(world, request)
    assert len(result.approved) == len(result.skipped) == 1
    with pytest.raises(ApiError, match="服务身份只读"):
        CustomsApprovalService(world[0], world[1]).approve_batch(request, "service:test")


def test_reapproval_waits_for_current_customs_version(world, ns):
    captured = []
    world[1].subscribe(InvoiceReady, lambda connection, event: captured.append(event))
    finance(world)
    approve(world, body(current(world)))
    original_review = captured[0].review_id
    save(ns, world[0], bundle([purchase(amounts=("130", "20"))], [customs("870", "2026-09-03T10:00:00Z")]))
    finance(world)
    assert len(rows(world[0], "SELECT * FROM task_tasks")) == 1
    assert not current(world).approval.approved
    approve(world, body(current(world)))
    assert len(rows(world[0], "SELECT * FROM task_tasks")) == 2
    assert len(captured) == 2 and captured[1].superseded_review_id == original_review
    assert len(rows(world[0], "SELECT * FROM review_records WHERE customs_approval_id IS NOT NULL")) == 2


def test_subscriber_failure_rolls_back_last_approval_and_release(world):
    finance(world)

    def fail(connection, event):
        raise RuntimeError("模拟后续订阅失败")

    world[1].subscribe(InvoiceReady, fail)
    with pytest.raises(RuntimeError, match="模拟后续"):
        approve(world, body(current(world)))
    assert rows(world[0], "SELECT * FROM review_customs_approvals") == []
    assert rows(world[0], "SELECT * FROM review_records WHERE customs_approval_id IS NOT NULL") == []
    assert rows(world[0], "SELECT * FROM task_tasks") == []


def test_mysql_concurrent_finance_and_customs_release_once(world):
    if world[0].dialect.name != "mysql":
        pytest.skip("双审核并发必须在 MySQL 验证")
    request, barrier = body(current(world)), Barrier(2)

    def run(action):
        barrier.wait()
        action()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run, lambda: finance(world)),
            pool.submit(run, lambda: approve(world, request)),
        ]
        for future in futures:
            future.result()
    assert len(rows(world[0], "SELECT * FROM review_records WHERE customs_approval_id IS NOT NULL")) == 1
    assert len(rows(world[0], "SELECT * FROM task_tasks")) == 1


def test_http_contract_rejects_invalid_scope_and_service_identity(world):
    import asyncio

    import httpx
    from backend.core.dependencies import current_owner
    from backend.core.middleware import register_error_handlers
    from backend.modules.review.controller.customs_receipt_controller import create_router
    from fastapi import FastAPI

    app = FastAPI()
    actor = {"value": USER}
    app.dependency_overrides[current_owner] = lambda: actor["value"]
    register_error_handlers(app)
    app.include_router(create_router(world[2], CustomsApprovalService(world[0], world[1])))

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = "/api/review/customs-receipts/approve-batch"
            assert (await client.post(path, json={"items": []})).status_code == 400
            request = body(current(world)).model_dump()
            duplicate = {**request, "items": request["items"] * 2}
            assert (await client.post(path, json=duplicate)).status_code == 400
            actor["value"] = "service:test"
            assert (await client.post(path, json=request)).status_code == 403
            actor["value"] = USER
            response = await client.post(path, json=request)
            assert response.status_code == 200 and len(response.json()["approved"]) == 1
            listed = await client.post("/api/review/customs-receipts/query", json={"status": "approved"})
            assert listed.status_code == 200
            payload = listed.json()
            assert payload["counts"]["approved"] == payload["total"] == 1
            assert payload["items"][0]["approval"]["approved"] is True

    asyncio.run(check())


def test_simplified_migration_preserves_existing_finance_records(schema_engine):
    from alembic import command
    from backend.manage import SCHEMA_INI, _config
    from backend.tests.test_schema_baseline import NOW
    from sqlalchemy import inspect, text

    config = _config(SCHEMA_INI, schema_engine.url.render_as_string(hide_password=False))
    command.downgrade(config, "0043_task_supplier_owners")
    with schema_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO review_records "
                "(ns_account, customs_declaration_id, revision, content_sha256, approved_by, approved_at) "
                "VALUES ('prod', 1, 1, :digest, 'user:test', :now)"
            ),
            {"digest": "a" * 64, "now": NOW},
        )
        before = dict(connection.execute(text("SELECT * FROM review_records")).mappings().one())
    command.upgrade(config, "head")
    with schema_engine.connect() as connection:
        after = dict(connection.execute(text("SELECT * FROM review_records")).mappings().one())
        assert after.pop("customs_approval_id") is None
        assert after == before
    assert "review_task_releases" not in inspect(schema_engine).get_table_names()


def test_simplified_migration_cannot_drop_approval_history(world):
    from alembic import command
    from backend.manage import SCHEMA_INI, _config

    finance(world)
    approve(world, body(current(world)))
    config = _config(SCHEMA_INI, world[0].url.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError, match="已有数据"):
        command.downgrade(config, "0043_task_supplier_owners")
    assert rows(world[0], "SELECT customs_approval_id FROM review_records")[0]["customs_approval_id"]
    assert len(rows(world[0], "SELECT * FROM task_tasks")) == 1
