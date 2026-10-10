"""供应商群配置的持久化、权限、版本及通知自动带出；不访问真实企微。"""

import pytest
from alembic import command
from alembic.config import Config
from backend.app import create_app
from backend.core.config import ROOT
from backend.core.errors import ApiError
from backend.database import make_engine
from backend.modules.business.entity import load_tables
from backend.modules.business.public import SupplierDirectory
from backend.modules.reconciliation import group_dao
from backend.modules.reconciliation.group_dto import GroupQuery, GroupSave, WecomGroupQuery
from backend.modules.reconciliation.group_entity import bindings
from backend.modules.reconciliation.group_service import SupplierGroupService
from backend.tests.test_api import login
from backend.tests.test_finance_list import OWNER
from backend.tests.test_finance_list import local_source as local_source
from backend.tests.test_task_documents import ContractSource, task_service
from backend.tests.test_task_notifications import draft, record
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import MetaData, Table, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError


@pytest.fixture
def suppliers(local_source):
    bindings.create(local_source.engine)
    with local_source.engine.begin() as connection:
        orders = load_tables(connection)["purchase_orders"]
        connection.execute(
            orders.update().where(orders.c.id.in_([1, 2, 3, 4])).values(supplier_identifier="vendor1")
        )
        connection.execute(
            orders.update()
            .where(orders.c.id == 5)
            .values(supplier_identifier="vendor2", supplier_name="供应商")
        )
    return SupplierDirectory(local_source.engine)


class FakeWecom:
    def __init__(self):
        self.calls = []
        self.employee = "采购员"
        self.userid = "buyer1"
        self.fail = False

    def group(self, chat_id):
        self.calls.append(chat_id)
        if self.fail:
            raise ApiError(502, "企微查询失败")
        return {
            "groupName": "供应商采购群" if chat_id != "wr_new" else "新的默认群",
            "chatId": chat_id,
            "employee": self.employee,
            "userid": self.userid,
            "memberCount": 8,
            "createdAt": 100,
        }

    def groups(self, *, refresh=False):
        return {"items": [self.group("wr_test_group"), self.group("wr_duplicate")], "unavailableCount": 1}


def service(context, suppliers):
    return SupplierGroupService(suppliers.engine, suppliers, OWNER, wecom=FakeWecom())


def binding(**overrides):
    return GroupSave(
        **{
            "account": "prod",
            "supplierId": "vendor1",
            "revision": 0,
            "chatId": "wr_test_group",
            "enabled": True,
            **overrides,
        }
    )


def test_supplier_identity_account_and_name_isolation(context, local_source, suppliers):
    options = suppliers.read(OWNER)
    assert {(x["account"], x["supplierId"]) for x in options["items"]} == {
        ("prod", "vendor1"),
        ("prod", "vendor2"),
        ("sb", "vendor1"),
    }
    assert suppliers.read("user:other")["total"] == 0
    groups = service(context, suppliers)
    groups.save(OWNER, binding())
    groups.save(OWNER, binding(account="sb", chatId="wr_sb"))
    groups.save(OWNER, binding(supplierId="vendor2", chatId="wr_second"))
    assert groups.browse(OWNER, GroupQuery(keyword="wr_second")).items[0].supplierId == "vendor2"
    assert groups.browse(OWNER, GroupQuery(keyword="%")).total == 0
    assert groups.browse("user:other", GroupQuery()).total == 0
    assert not groups.capability("service").allowed
    for owner in ("user:other", "service"):
        with pytest.raises(ApiError) as error:
            groups.save(owner, binding())
        assert error.value.status == 403
    with pytest.raises(ApiError) as error:
        groups.save(OWNER, binding(account="inaccessible"))
    assert error.value.status == 404
    with pytest.raises(ApiError):
        groups.save(OWNER, binding(supplierId="missing"))


def test_revision_disable_persistence_and_save_rollback(context, suppliers, monkeypatch):
    groups = service(context, suppliers)
    saved = groups.save(OWNER, binding())
    assert saved.revision == 1
    with pytest.raises(ApiError) as error:
        groups.save(OWNER, binding())
    assert error.value.status == 409
    disabled = groups.save(OWNER, binding(revision=1, enabled=False))
    assert disabled.revision == 2 and not disabled.enabled
    assert groups.browse(OWNER, GroupQuery(status="enabled")).total == 0
    assert service(context, suppliers).browse(OWNER, GroupQuery(status="disabled")).total == 1

    with pytest.raises(ApiError) as error:
        groups.save(OWNER, binding(revision=1))
    assert error.value.status == 409
    original_save = group_dao.save

    def fail(connection, values, revision):
        original_save(connection, values, revision)
        raise SQLAlchemyError("save failed")

    monkeypatch.setattr(group_dao, "save", fail)
    with pytest.raises(ApiError):
        groups.save(OWNER, binding(revision=2))
    persisted = service(context, suppliers).browse(OWNER, GroupQuery()).items[0]
    assert persisted.revision == 2 and not persisted.enabled


def test_task_prefill_does_not_overwrite_saved_or_sent_notifications(context, local_source, suppliers):
    followup, task, order = task_service(context, local_source, ContractSource())
    groups = service(context, suppliers)
    followup.supplier_groups = groups
    groups.save(OWNER, binding())
    detail = followup.detail(task.id, OWNER)
    assert detail.notification.groupName == "供应商采购群"
    assert detail.notification.employee == "采购员"
    assert detail.notification.supplierGroup.chatId == "wr_test_group"
    assert detail.notification.revision == 0 and not detail.notification.send.allowed
    followup.save_notification(task.id, draft(), OWNER)
    groups.save(OWNER, binding(revision=1, chatId="wr_new"))
    assert followup.detail(task.id, OWNER).notification.groupName == draft().groupName
    followup.prepare_document(task.id, order, OWNER)
    sent = followup.save_notification(task.id, record(), OWNER, record=True)
    original_history = sent.notification.history
    groups.save(OWNER, binding(revision=2, enabled=False))
    again = followup.detail(task.id, OWNER)
    assert again.notification.supplierGroup is None
    assert again.notification.history == original_history
    assert again.task.status == "awaiting_invoice"


def test_unconfigured_or_missing_supplier_identity_is_not_guessed(context, local_source, suppliers):
    followup, task, _ = task_service(context, local_source, ContractSource())
    assert followup.detail(task.id, OWNER).notification.supplierGroup is None
    groups = service(context, suppliers)
    followup.supplier_groups = groups
    groups.save(OWNER, binding(account="sb"))
    assert followup.detail(task.id, OWNER).notification.supplierGroup is None


def test_api_auth_validation_and_save(context, local_source, suppliers):
    app = create_app(context.settings, context.ns, context.engine, local_source.engine, wecom=FakeWecom())
    root = "/api/reconciliation/supplier-groups"
    headers = {"Origin": context.settings.origin}
    with TestClient(app) as client:
        assert client.post(root + "/save", json=binding().model_dump(), headers=headers).status_code == 401
        login(client, context)
        response = client.post(root + "/save", json=binding().model_dump(), headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["supplierName"] == "供应商"
        with context.engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(bindings)) == 0
        with local_source.engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(bindings)) == 1
        # 验证正式装配的任务详情也从业务库读取，不能仅证明独立 Service 可用。
        _, task, _ = task_service(context, local_source, ContractSource())
        detail = client.get(f"/api/reconciliation/invoice-tasks/{task.id}")
        assert detail.status_code == 200
        assert detail.json()["notification"]["supplierGroup"]["chatId"] == "wr_test_group"
        assert (
            client.post(
                root + "/save", json={**binding().model_dump(), "owner": OWNER}, headers=headers
            ).status_code
            == 400
        )
        assert client.post(root + "/query", json={"pageSize": 0}, headers=headers).status_code == 400
        for path in ("/directory/import", "/directory/query"):
            assert root + path not in app.openapi()["paths"]
            assert client.post(root + path, json={}, headers=headers).status_code == 405
        assert (
            client.post(root + "/suppliers/query", json={"keyword": "vendor1"}, headers=headers).json()[
                "total"
            ]
            == 2
        )


@pytest.mark.parametrize(
    "field,value", [("chatId", ""), ("userid", " "), ("employee", " "), ("revision", -1), ("enabled", "true")]
)
def test_invalid_binding_fields(field, value):
    with pytest.raises(ValidationError):
        binding(**{field: value})


def test_simplification_migration_preserves_current_binding(tmp_path):
    url = f"sqlite:///{tmp_path / 'groups-upgrade.sqlite'}"
    config = Config(str(ROOT / "backend" / "legacy_migrations" / "app.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "0008_contract_metadata")
    engine = make_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                bindings.insert().values(
                    owner=OWNER,
                    account="prod",
                    supplier_id="vendor1",
                    supplier_key="key1",
                    supplier_name="供应商",
                    group_name="采购群",
                    chat_id="wr_1",
                    employee="采购员",
                    userid="buyer1",
                    enabled=True,
                    revision=3,
                    updated_at=100,
                )
            )
            old = MetaData()
            history = Table("finance_supplier_group_history", old, autoload_with=connection)
            directory = Table("finance_wecom_group_directory", old, autoload_with=connection)
            connection.execute(
                history.insert().values(
                    owner=OWNER,
                    account="prod",
                    supplier_id="vendor1",
                    revision=3,
                    at=100,
                    payload="{}",
                )
            )
            connection.execute(
                directory.insert().values(
                    owner=OWNER,
                    chat_id="wr_1",
                    group_name="采购群",
                    employee="采购员",
                    userid="buyer1",
                    updated_at=100,
                )
            )
            before = dict(connection.execute(select(bindings)).mappings().one())
        command.upgrade(config, "head")
        with engine.connect() as connection:
            tables = inspect(connection).get_table_names()
            assert "finance_supplier_group_history" not in tables
            assert "finance_wecom_group_directory" not in tables
            assert dict(connection.execute(select(bindings)).mappings().one()) == before
    finally:
        engine.dispose()


def test_group_database_missing_or_unavailable_does_not_fall_back(context, suppliers, local_source):
    with pytest.raises(ApiError) as error:
        SupplierGroupService(None, suppliers, OWNER).browse(OWNER, GroupQuery())
    assert error.value.status == 503
    groups = service(context, suppliers)
    groups.save(OWNER, binding())
    with context.engine.begin() as connection:
        # 应用库即使残留旧映射也不能回退读取。
        connection.execute(
            bindings.insert().values(
                owner=OWNER,
                account="prod",
                supplier_id="vendor1",
                supplier_key="legacy-key",
                supplier_name="旧供应商",
                group_name="旧群",
                chat_id="wr_legacy",
                employee="旧员工",
                userid="legacy",
                enabled=True,
                revision=1,
                updated_at=1,
            )
        )
    assert groups.browse(OWNER, GroupQuery()).items[0].chatId == "wr_test_group"
    bindings.drop(local_source.engine)
    with pytest.raises(ApiError) as error:
        groups.browse(OWNER, GroupQuery())
    assert error.value.status == 503
    followup, task, _ = task_service(context, local_source, ContractSource())
    followup.supplier_groups = groups
    detail = followup.detail(task.id, OWNER)
    assert detail.notification.supplierGroup is None
    assert "群配置读取失败" in detail.notification.groupConfigReason
    assert not detail.notification.send.allowed


def test_wecom_search_preserves_duplicate_names_and_requires_permission(context, suppliers):
    groups = service(context, suppliers)
    result = groups.search_wecom(OWNER, WecomGroupQuery(keyword="采购"))
    assert result.total == 2 and result.unavailableCount == 1
    assert len({item.chatId for item in result.items}) == 2
    assert groups.search_wecom(OWNER, WecomGroupQuery(keyword="不存在")).total == 0
    with pytest.raises(ApiError) as error:
        groups.search_wecom("service", WecomGroupQuery(keyword="采购"))
    assert error.value.status == 403


def test_save_rechecks_owner_and_can_disable_without_wecom(context, suppliers):
    groups = service(context, suppliers)
    groups.wecom.userid = "new_owner"
    groups.wecom.employee = "新群主"
    saved = groups.save(OWNER, binding())
    assert saved.userid == "new_owner" and saved.employee == "新群主"
    groups.wecom.fail = True
    disabled = groups.save(OWNER, binding(revision=1, enabled=False))
    assert not disabled.enabled and disabled.userid == "new_owner"
    with pytest.raises(ApiError):
        groups.save(OWNER, binding(revision=2, enabled=True))
    with pytest.raises(ApiError):
        groups.save(OWNER, binding(revision=2, enabled=False, chatId="wr_forged"))
    assert groups.browse(OWNER, GroupQuery()).items[0].revision == 2


@pytest.mark.parametrize("field", ["groupName", "userid", "employee"])
def test_client_cannot_supply_group_identity_fields(field):
    with pytest.raises(ValidationError):
        binding(**{field: "forged"})
