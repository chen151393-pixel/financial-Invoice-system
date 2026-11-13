"""供应商人员关联：隔离数据库验证时间归属、批量原子性、预览冲突与任务交接。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from backend.app import create_app
from backend.core.errors import ApiError
from backend.manage import SCHEMA_INI, _config
from backend.modules.identity.dao import user_dao
from backend.modules.review.public import ApprovedLine, ReviewApproved
from backend.modules.task.dao import supplier_owner_dao, task_dao, task_owner_dao
from backend.modules.task.dto.supplier_owner_dto import OwnerChange, OwnerQuery, OwnerSave
from backend.modules.task.entity import supplier_owners
from backend.modules.task.public import owner_at_time
from backend.modules.task.service.supplier_owner_reader import china_today
from backend.modules.task.service.supplier_owner_service import SupplierOwnerService
from backend.modules.task.service.task_generation_service import on_review_approved
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import engine as engine  # 共用隔离库夹具
from backend.tests.test_source_storage import ns as ns
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

ACTOR = "user:admin"


@pytest.fixture
def setup(engine, ns):
    first, second = purchase(), purchase("201")
    second[1]["custrecord_swc_subpo_class"] = {"id": "4", "refName": "采购公司B"}
    save(ns, engine, bundle([first, second], [customs("870")]))
    now = datetime.now(UTC).replace(tzinfo=None)
    with engine.begin() as connection:
        for index, name in enumerate(("王萍", "范宇洁", "徐彩凤"), 1):
            user_dao.save(
                connection,
                {
                    "user_id": f"owner-{index}",
                    "open_id": f"open-{index}",
                    "union_id": None,
                    "name": name,
                    "avatar_url": None,
                    "active": True,
                    "inactive_reason": None,
                },
                now,
            )
    service = SupplierOwnerService(engine)
    rows = service.browse(OwnerQuery()).items
    assert len(rows) == 2 and rows[0].supplierId == rows[1].supplierId
    return service, rows


def change(rows, member=1, day=None, transfer=False):
    return OwnerChange(
        items=[{"supplierId": r.supplierId, "companyId": r.companyId, "revision": r.revision} for r in rows],
        memberId=member,
        effectiveDate=day or china_today(),
        transferOpenTasks=transfer,
        reason="采购分工调整",
    )


def persist(service, body):
    preview = service.preview(body, ACTOR)
    return service.save(OwnerSave(**body.model_dump(), previewToken=preview.previewToken), ACTOR)


def make_task(engine, row, *, review=1, status="documents_pending"):
    now = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
    with engine.begin() as connection:
        return task_dao.insert_task(
            connection,
            {
                "review_id": review,
                "ns_account": "prod",
                "customs_declaration_id": 1,
                "supplier_id": row.supplierId,
                "company_id": row.companyId,
                "group_key": str(review).zfill(64),
                "status": status,
                "review_revision": 1,
            },
            now,
        )


def test_pair_specific_assignment_and_source_pair_options(setup):
    service, rows = setup
    options = service.options()
    assert len(options.suppliers) == 1 and len(options.companies) == 2 and len(options.members) == 3
    assert persist(service, change([rows[0]])).saved == 1
    assert persist(service, change([rows[1]], member=2)).saved == 1
    result = service.browse(OwnerQuery())
    assert [r.current.memberName for r in result.items] == ["王萍", "范宇洁"]
    assert service.browse(OwnerQuery(memberId=2)).items[0].companyId == rows[1].companyId
    assert service.browse(OwnerQuery(status="unassigned")).total == 0
    assert service.browse(OwnerQuery(supplierName="不存在")).total == 0
    page = service.browse(OwnerQuery(page=2, pageSize=1))
    assert page.total == 2 and len(page.items) == 1 and page.pages == 2


def test_single_table_http_preview_save_and_history(context, engine, setup):
    _, rows = setup
    with TestClient(create_app(context.settings, context.ns, engine)) as client:
        headers = {"Origin": context.settings.origin}
        assert (
            client.post(
                "/api/session",
                json={"username": "admin", "password": context.settings.admin_password},
                headers=headers,
            ).status_code
            == 200
        )
        body = change([rows[0]]).model_dump(mode="json")
        preview = client.post("/api/task/supplier-owners/preview", json=body, headers=headers)
        assert preview.status_code == 200
        saved = client.post(
            "/api/task/supplier-owners/save",
            json={**body, "previewToken": preview.json()["previewToken"]},
            headers=headers,
        )
        assert saved.status_code == 200 and saved.json()["saved"] == 1
        history = client.get(f"/api/task/supplier-owners/{rows[0].supplierId}/{rows[0].companyId}/history")
        assert history.status_code == 200 and history.json()["items"][0]["memberName"] == "王萍"


def test_future_and_same_day_versions_keep_full_history(setup):
    service, rows = setup
    persist(service, change([rows[0]], day=china_today() - timedelta(days=10)))
    current = service.browse(OwnerQuery()).items[0]
    future = china_today() + timedelta(days=5)
    persist(service, change([current], member=2, day=future))
    current = service.browse(OwnerQuery()).items[0]
    assert current.current.memberName == "王萍" and current.scheduled[0].memberName == "范宇洁"
    persist(service, change([current], member=3, day=future))
    current = service.browse(OwnerQuery()).items[0]
    assert len(current.scheduled) == 1 and current.scheduled[0].memberName == "徐彩凤"
    assert len(service.history(current.supplierId, current.companyId).items) == 3
    assert service.browse(OwnerQuery(status="scheduled")).total == 1


def test_create_future_only_and_dates_are_beijing():
    assert china_today(datetime(2026, 11, 12, 16, 0)) == date(2026, 11, 13)


def test_task_generation_freezes_owner_and_later_mapping_does_not_rewrite(setup, engine):
    service, rows = setup
    persist(service, change([rows[0]]))
    with engine.begin() as connection:
        on_review_approved(
            connection,
            ReviewApproved(
                1,
                None,
                "prod",
                1,
                "CD870",
                1,
                ACTOR,
                (
                    ApprovedLine(
                        1,
                        1,
                        1,
                        rows[0].supplierId,
                        rows[0].companyId,
                        "SUB-200",
                        "CNY",
                        Decimal("1"),
                        "瓶",
                        Decimal("10"),
                        1,
                    ),
                ),
            ),
        )
        task_id = connection.execute(text("SELECT id FROM task_tasks")).scalar_one()
        before = task_owner_dao.timeline(connection, task_id)
        assert before[0]["member_name"] == "王萍"
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM task_events WHERE task_id=:id"), {"id": task_id}
            ).scalar_one()
            == 1
        )
    persist(service, change([service.browse(OwnerQuery()).items[0]], member=2))
    with engine.connect() as connection:
        assert task_owner_dao.timeline(connection, task_id) == before
        assert (
            owner_at_time(connection, task_id, datetime.now(UTC).replace(tzinfo=None))["member_name"]
            == "王萍"
        )


def test_open_tasks_transfer_but_completed_and_previous_facts_keep_owner(setup, engine):
    service, rows = setup
    persist(service, change([rows[0]], day=china_today() - timedelta(days=10)))
    open_id = make_task(engine, rows[0])
    done_id = make_task(engine, rows[0], review=2, status="completed")
    with engine.begin() as connection:
        old = supplier_owner_dao.effective(connection, rows[0].supplierId, rows[0].companyId, china_today())
        for pk in (open_id, done_id):
            task_owner_dao.append(
                connection,
                pk,
                old,
                datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2),
                "原始归属",
                ACTOR,
                datetime.now(UTC).replace(tzinfo=None),
            )
    before_transfer = datetime.now(UTC).replace(tzinfo=None)
    current = service.browse(OwnerQuery()).items[0]
    result = persist(service, change([current], member=2, transfer=True))
    assert result.transferredTasks == 1
    with engine.connect() as connection:
        assert owner_at_time(connection, open_id, before_transfer)["member_name"] == "王萍"
        assert (
            owner_at_time(connection, open_id, datetime.now(UTC).replace(tzinfo=None))["member_name"]
            == "范宇洁"
        )
        assert (
            owner_at_time(connection, done_id, datetime.now(UTC).replace(tzinfo=None))["member_name"]
            == "王萍"
        )
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM task_events WHERE event_type='owner_transferred'")
            ).scalar()
            == 1
        )


def test_legacy_task_unknown_before_explicit_handover(setup, engine):
    service, rows = setup
    task_id = make_task(engine, rows[0])
    before = datetime.now(UTC).replace(tzinfo=None)
    persist(service, change([rows[0]], member=2, transfer=True))
    with engine.connect() as connection:
        assert owner_at_time(connection, task_id, before) is None
        assert owner_at_time(connection, task_id, datetime.now(UTC).replace(tzinfo=None))["member_id"] == 2


def test_stale_association_revision_rejects_whole_batch(setup):
    service, rows = setup
    preview = service.preview(change(rows), ACTOR)
    persist(service, change([rows[1]], member=2))
    with pytest.raises(ApiError, match="已被修改"):
        service.save(OwnerSave(**change(rows).model_dump(), previewToken=preview.previewToken), ACTOR)
    assert service.history(rows[0].supplierId, rows[0].companyId).items == []


def test_task_created_or_closed_after_preview_rejects_save(setup, engine):
    service, rows = setup
    body = change(rows)
    preview = service.preview(body, ACTOR)
    make_task(engine, rows[0])
    with pytest.raises(ApiError, match="预览后"):
        service.save(OwnerSave(**body.model_dump(), previewToken=preview.previewToken), ACTOR)
    assert service.browse(OwnerQuery(status="assigned")).total == 0


def test_batch_database_failure_rolls_back_all_pairs(setup, engine, monkeypatch):
    service, rows = setup
    body = change(rows)
    preview = service.preview(body, ACTOR)
    original = supplier_owner_dao.append
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise IntegrityError("test", {}, Exception("conflict"))
        return original(*args, **kwargs)

    monkeypatch.setattr(supplier_owner_dao, "append", fail_second)
    with pytest.raises(ApiError):
        service.save(OwnerSave(**body.model_dump(), previewToken=preview.previewToken), ACTOR)
    with engine.connect() as connection:
        assert connection.execute(select(supplier_owners)).all() == []


def test_service_is_read_only_and_invalid_member_rejected(setup):
    service, rows = setup
    with pytest.raises(ApiError) as error:
        service.preview(change(rows), "service:feishu")
    assert error.value.status == 403
    with pytest.raises(ApiError, match="负责人不存在"):
        service.preview(change(rows, member=9999), ACTOR)
    with pytest.raises(ValidationError):
        OwnerChange(**{**change(rows).model_dump(), "items": [change(rows).items[0], change(rows).items[0]]})


def test_future_handover_is_not_applied_early(setup):
    service, rows = setup
    body = change(rows, day=china_today() + timedelta(days=1))
    assert service.preview(body, ACTOR).transferAllowed is False
    with pytest.raises(ApiError, match="未来生效"):
        service.preview(body.model_copy(update={"transferOpenTasks": True}), ACTOR)
    persist(service, body)
    result = service.browse(OwnerQuery())
    assert all(r.current is None and r.scheduled for r in result.items)


def test_cross_account_reference_rejected_and_inactive_member_not_offered(setup, engine):
    service, rows = setup
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE source_companies SET ns_account='other' WHERE id=:id"), {"id": rows[0].companyId}
        )
        connection.execute(text("UPDATE identity_users SET active=0 WHERE id=3"))
    assert 3 not in {r.id for r in service.options().members}
    with pytest.raises(ApiError, match="同一 NS"):
        service.preview(change([rows[0]]), ACTOR)


def test_migration_refuses_dropping_attribution_history(setup, engine):
    service, rows = setup
    persist(service, change([rows[0]]))
    with pytest.raises(RuntimeError, match="禁止自动降级"):
        command.downgrade(
            _config(SCHEMA_INI, engine.url.render_as_string(hide_password=False)),
            "0042_review_customs_receipts",
        )
    assert service.browse(OwnerQuery(status="assigned")).total == 1
