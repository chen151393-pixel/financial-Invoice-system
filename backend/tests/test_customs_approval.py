"""双审核门槛、版本、权限、异常人工确认、幂等、回滚与可选 MySQL 并发。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from backend.app import create_events
from backend.core.errors import ApiError
from backend.modules.review.dto.customs_receipt_dto import CustomsApproveRequest, CustomsReceiptQuery
from backend.modules.review.dto.review_dto import ApproveRequest
from backend.modules.review.public import InvoiceReady
from backend.modules.review.service.customs_approval_service import CustomsApprovalService
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import ns as ns

USER = "user:admin"


@pytest.fixture
def world(schema_engine, ns):
    engine = schema_engine
    events = create_events()
    save(ns, engine, bundle([purchase()], [customs("870")]))
    receipts = CustomsReceiptService(engine)
    _import(
        receipts,
        [
            row("REAL870", "01", "墨水", "个", 6),
            row("REAL870", "02", "墨水", "个", 4),
            row("REAL870", "03", "清洗液", "个", 10),
        ],
    )
    return engine, events, receipts, ReviewService(engine, DeclarationService(engine), events)


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


def approve(world, request):
    return CustomsApprovalService(world[0], world[1]).approve_batch(request, USER)


@pytest.mark.parametrize("first", ["finance", "customs"])
def test_both_orders_release_once_and_audit(world, first):
    request = body(current(world))
    actions = {"finance": lambda: finance(world), "customs": lambda: approve(world, request)}
    actions[first]()
    assert rows(world[0], "SELECT * FROM task_tasks") == []
    actions["customs" if first == "finance" else "finance"]()
    assert len(rows(world[0], "SELECT * FROM task_tasks")) == 1
    assert len(rows(world[0], "SELECT * FROM task_lines")) == 2
    assert len(approve(world, request).approved) == 1
    finance(world)
    assert len(rows(world[0], "SELECT * FROM review_records WHERE customs_approval_id IS NOT NULL")) == 1
    assert len(rows(world[0], "SELECT * FROM review_customs_approvals")) == 1
    assert current(world).approval.label == "自动审核通过"


def test_auto_rejects_differences_manual_requires_note(world):
    _import(world[2], [row("REAL870", "01", "墨水", "个", 9), row("REAL870", "02", "清洗液", "个", 10)])
    item = current(world)
    assert item.approval.allowed and not item.approval.autoAllowed
    assert "仅明细一致" in approve(world, body(item)).skipped[0].reason
    assert "填写人工审核说明" in approve(world, body(item, "manual")).skipped[0].reason
    assert approve(world, body(item, "manual", "已逐项核实差异")).approved
    assert current(world).approval.note == "已逐项核实差异"


def test_stale_source_and_reimport_invalidate_approval(world, ns):
    original = current(world)
    approve(world, body(original))
    save(ns, world[0], bundle([purchase(amounts=("130", "20"))], [customs("870", "2026-09-03T10:00:00Z")]))
    assert not current(world).approval.approved
    assert "已变化" in approve(world, body(original)).skipped[0].reason
    finance(world)
    assert rows(world[0], "SELECT * FROM task_tasks") == []
    request = body(current(world))
    _import(
        world[2],
        [row("REAL870", "01", "墨水", "个", 10, "NEW"), row("REAL870", "02", "清洗液", "个", 10, "NEW")],
    )
    assert "已变化" in approve(world, request).skipped[0].reason
    assert not current(world).approval.approved
    assert approve(world, body(current(world))).approved
    assert len(rows(world[0], "SELECT * FROM task_tasks")) == 1


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
