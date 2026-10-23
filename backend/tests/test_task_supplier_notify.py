"""供应商档案"是否开启供应商通知"（2026-10-23）与开票跟进按供应商筛选。

关闭通知后，之后的财务审核不生成该供应商的开票任务；已有任务不变。SQLite 隔离库，合成 NS 数据。
"""

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.source.public import SourceDirectory
from backend.modules.task.dto.supplier_group_dto import SupplierNotifySave, SupplierProfileQuery
from backend.modules.task.dto.task_dto import TaskListQuery
from backend.modules.task.service.supplier_profile_service import SupplierProfileService
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from backend.tests.test_task import USER, approve, task_rows
from backend.tests.test_task import app_services as app_services  # 共用夹具
from fastapi.testclient import TestClient


@pytest.fixture
def profiles(engine):
    return SupplierProfileService(engine, SourceDirectory(engine))


def other_supplier(order_id, customs_id):
    order_id, head, lines = purchase(order_id, customs_id)
    head["custrecord_swc_subpo_vendor"] = {"id": "78", "refName": "第二供应商"}
    return order_id, head, lines


def supplier_id(engine, name):
    found = rows(engine, "SELECT id FROM source_suppliers WHERE name = :n", n=name)
    return str(found[0]["id"])


def notify(profiles, supplier, enabled, revision, actor=USER):
    return profiles.set_notify(
        SupplierNotifySave(supplierId=supplier, enabled=enabled, revision=revision), actor
    )


def profile(profiles, supplier):
    items = profiles.browse(SupplierProfileQuery(pageSize=50), USER).items
    return next(item for item in items if item.supplierId == supplier)


def test_closed_supplier_gets_no_task_and_reopening_affects_later_reviews(ns, engine, app_services, profiles):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    save(ns, engine, bundle([purchase("210", "890")], [customs("890")]))
    supplier = supplier_id(engine, "上海 供应商（有限）公司")
    assert profile(profiles, supplier).notify.enabled  # 没有设置记录：默认开启
    closed = notify(profiles, supplier, False, 0)
    assert not closed.enabled and closed.revision == 1 and closed.updatedBy == USER
    approve(app_services, "CD870")
    assert task_rows(engine) == []  # 审核照常保存，但不生成开票任务
    assert len(rows(engine, "SELECT id FROM review_records WHERE status = 'active'")) == 1
    notify(profiles, supplier, True, 1)
    approve(app_services, "CD890")
    assert [task["record_no"] for task in task_rows(engine)] == ["CD890"]


def test_closing_later_keeps_existing_tasks(ns, engine, app_services, profiles):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(app_services, "CD870")
    notify(profiles, supplier_id(engine, "上海 供应商（有限）公司"), False, 0)
    assert [task["status"] for task in task_rows(engine)] == ["documents_pending"]


def test_only_closed_supplier_is_skipped_within_one_declaration(ns, engine, app_services, profiles):
    save(ns, engine, bundle([purchase("200", "870"), other_supplier("210", "870")], [customs("870")]))
    notify(profiles, supplier_id(engine, "第二供应商"), False, 0)
    approve(app_services, "CD870")
    tasks = task_rows(engine)
    assert [str(task["supplier_id"]) for task in tasks] == [supplier_id(engine, "上海 供应商（有限）公司")]


def test_notify_setting_version_identity_and_existence(ns, engine, profiles):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    supplier = supplier_id(engine, "上海 供应商（有限）公司")
    notify(profiles, supplier, False, 0)
    for revision in (0, 5):
        with pytest.raises(ApiError) as error:
            notify(profiles, supplier, True, revision)
        assert error.value.status == 409
    with pytest.raises(ApiError) as error:
        notify(profiles, supplier, True, 1, actor="service:feishu")
    assert error.value.status == 403
    with pytest.raises(ApiError) as error:
        notify(profiles, "999999", True, 0)
    assert error.value.status == 404
    current = profile(profiles, supplier).notify
    assert not current.enabled and current.revision == 1


def test_task_list_filters_by_supplier_with_options(ns, engine, app_services):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    save(ns, engine, bundle([other_supplier("210", "890")], [customs("890")]))
    approve(app_services, "CD870")
    approve(app_services, "CD890")
    tasks = app_services["tasks"]
    listed = tasks.browse(TaskListQuery())
    assert [option.name for option in listed.suppliers] == sorted(["上海 供应商（有限）公司", "第二供应商"])
    second = supplier_id(engine, "第二供应商")
    for group_by in ("supplier", "declaration"):
        filtered = tasks.browse(TaskListQuery(supplierId=second, groupBy=group_by))
        assert filtered.total == 1 and filtered.counts.tasks == 1
        assert [task.recordNumber for group in filtered.groups for task in group.tasks] == ["CD890"]
    assert tasks.browse(TaskListQuery(supplierId="999999")).total == 0
    with pytest.raises(ValueError):
        TaskListQuery(supplierId="abc")


def test_http_notify_route(context, ns, engine):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    supplier = supplier_id(engine, "上海 供应商（有限）公司")
    app = create_app(context.settings, context.ns, engine)
    path = "/api/tasks/supplier-groups/profiles/notify"
    with TestClient(app) as client:
        assert (
            client.post(path, json={"supplierId": supplier, "enabled": False, "revision": 0}).status_code
            == 401
        )
        headers = {"Origin": context.settings.origin}
        login = client.post(
            "/api/session",
            headers=headers,
            json={"username": "admin", "password": context.settings.admin_password},
        )
        assert login.status_code == 200
        assert (
            client.post(
                path, json={"supplierId": "x", "enabled": False, "revision": 0}, headers=headers
            ).status_code
            == 400
        )
        saved = client.post(
            path, json={"supplierId": supplier, "enabled": False, "revision": 0}, headers=headers
        )
        assert saved.status_code == 200 and saved.json()["enabled"] is False
        listed = client.post("/api/tasks/supplier-groups/profiles/query", json={}, headers=headers)
        item = next(row for row in listed.json()["items"] if row["supplierId"] == supplier)
        assert item["notify"] == {**item["notify"], "enabled": False, "revision": 1}
