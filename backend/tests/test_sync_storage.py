"""分页保存复用完整主从存储；MySQL测试只使用隔离测试库。"""

from copy import deepcopy

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.business import dao
from backend.modules.business.entity import load_tables
from backend.modules.business.storage_service import StorageService
from backend.modules.source.service.ns_reader import PlReader
from backend.tests.test_pl_storage import configured_ns
from backend.tests.test_pl_storage import mysql_storage as mysql_storage
from fastapi.testclient import TestClient
from sqlalchemy import select


def page(ns, kind="purchase", ids=("10", "11")):
    return {
        "rows": [{"id": i, "record": {**deepcopy(ns.data[kind, i]), "id": i}} for i in ids],
        "count": len(ids),
        "offset": 0,
        "hasMore": False,
        "nextOffset": None,
    }


def complete_ns(ns):
    ns.data["pl", "1"] = {"name": "PL001"}
    return ns


def test_complete_page_reads_other_pl_and_independent_customs():
    ns = complete_ns(configured_ns())
    bundle = PlReader(ns).collect_records("sub-purchase-orders", page(ns)["rows"])
    assert len(bundle["purchases"]) == 2
    assert len(bundle["customs"]) == 1
    assert len(bundle["customs"][0][2]) == 3
    assert bundle["pl_names"] == {"1": "PL001", "9": "PL009"}
    assert ns.calls.count(("customs", "20")) == 1
    bundle = PlReader(ns).collect_records("customs-declarations", page(ns, "customs", ("20",))["rows"])
    assert len(bundle["purchases"]) == 2
    assert bundle["customs_purchase_membership"] == {"20": ["10", "11"]}
    assert len(bundle["customs"][0][2]) == 3


def test_missing_pl_or_wrong_parent_prevents_save():
    ns = complete_ns(configured_ns())
    ns.data["pl", "1"] = {}
    with pytest.raises(ApiError, match="PL单号"):
        PlReader(ns).collect_records("sub-purchase-orders", page(ns)["rows"])
    ns.data["purchase_line", "100"]["parent"] = {"id": "other"}
    with pytest.raises(ApiError, match="所属"):
        PlReader(ns).collect_records("sub-purchase-orders", page(ns)["rows"])


def test_storage_unavailable_and_unsupported_stop_before_reading():
    service = StorageService(configured_ns(), None)

    def unexpected_read():
        pytest.fail("不应调用 NS")

    with pytest.raises(ApiError, match="独立存储映射"):
        service.sync_page("purchase-orders", unexpected_read, "owner")
    with pytest.raises(ApiError, match="尚未配置"):
        service.sync_page("customs-declarations", unexpected_read, "owner")


def test_save_endpoint_keeps_identity_and_dto_checks(context):
    with TestClient(create_app(context.settings, context.ns, context.engine)) as client:
        path = "/api/ns/sync/sub-purchase-orders/pull-save"
        assert client.post(path, json={}).status_code == 401
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        assert client.post(path, json={"owner": "other"}, headers=headers).status_code == 400
        assert client.post(path, json={"offset": 1}, headers=headers).status_code == 400


def test_mysql_page_repeat_and_customs_only(mysql_storage):
    service, ns, owner = mysql_storage
    complete_ns(ns)
    first = service.sync_page("sub-purchase-orders", lambda: page(ns), owner)
    assert first["storage"]["purchase"]["created"] == 2
    assert first["storage"]["customs"]["created"] == 1
    assert service.query("PL009", 1, owner)["total"] == 1
    before = service.query("PL001", 1, owner)
    second = service.sync_page("sub-purchase-orders", lambda: page(ns), owner)
    assert second["storage"]["purchase"]["created"] == 0
    assert second["storage"]["purchase"]["updated"] == 2
    assert [(r["source"], r["id"]) for r in before["rows"]] == [
        (r["source"], r["id"]) for r in service.query("PL001", 1, owner)["rows"]
    ]
    other = service.sync_page("customs-declarations", lambda: page(ns, "customs", ("20",)), owner + "-other")
    assert other["storage"]["customs"]["created"] == 1
    assert other["storage"]["purchase"]["created"] == 2
    assert service.query("PL001", 1, owner + "-other")["total"] == 4


def test_mysql_page_rollback_empty_page_and_shared_lock(mysql_storage, monkeypatch):
    service, ns, owner = mysql_storage
    complete_ns(ns)
    service.sync_page("sub-purchase-orders", lambda: page(ns), owner)
    original = dao.save_document

    def fail_second(connection, table, *args):
        if table.name == "purchase_orders":
            raise ApiError(422, "故障注入")
        return original(connection, table, *args)

    ns.data["customs", "20"]["number"] = "CHANGED"
    monkeypatch.setattr(dao, "save_document", fail_second)
    with pytest.raises(ApiError, match="故障注入"):
        service.sync_page("sub-purchase-orders", lambda: page(ns), owner)
    assert all(r["values"]["declaration"] != "CHANGED" for r in service.query("PL001", 1, owner)["rows"])
    monkeypatch.setattr(dao, "save_document", original)
    empty = service.sync_page("sub-purchase-orders", lambda: page(ns, ids=()), owner)
    assert empty["storage"]["purchase"]["updated"] == 0
    assert service.query("PL001", 1, owner)["total"] == 4

    def while_locked():
        with pytest.raises(ApiError, match="已有"):
            service.sync("PL001", owner)
        return page(ns)

    service.sync_page("sub-purchase-orders", while_locked, owner)
    tenant, account = service.scope(owner)
    with service.engine.connect() as connection:
        table = load_tables(connection)["purchase_orders"]
        rows = (
            connection.execute(
                select(table).where(table.c.tenant_id == tenant, table.c.ns_account == account)
            )
            .mappings()
            .all()
        )
        assert len(rows) == 2
        assert all(row["detail_sync_status"] == "complete" for row in rows)


def test_mysql_page_http_commit(context, mysql_storage):
    service, ns, _ = mysql_storage
    complete_ns(ns)
    settings = context.settings
    settings.pl_lookup = ns.settings.pl_lookup
    settings.record_types = ns.settings.record_types
    settings.account = ns.settings.account
    settings.missing = lambda: []
    ns.settings = settings
    original = ns.request

    def request(method, record_type, record_id=None, **kwargs):
        if record_id is None:
            return {"data": {"items": [{"id": "10"}, {"id": "11"}], "hasMore": False}}
        return {"data": {**original(method, record_type, record_id, **kwargs)["data"], "id": record_id}}

    ns.request = request
    original_validate = ns.validate
    ns.validate = lambda kind, record_id=None: original_validate(kind, record_id) if record_id else None
    # 使用随机认证身份，复用fixture的清理范围。
    owner = mysql_storage[2]
    app = create_app(settings, ns, context.engine, service.engine)
    from backend.core.dependencies import current_owner

    app.dependency_overrides[current_owner] = lambda: owner
    with TestClient(app) as client:
        response = client.post("/api/ns/sync/sub-purchase-orders/pull-save", json={"limit": 20})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["storage"]["purchase"]["created"] == 2
        assert result["count"] == 2
        assert service.query("PL001", 1, owner)["total"] == 4
