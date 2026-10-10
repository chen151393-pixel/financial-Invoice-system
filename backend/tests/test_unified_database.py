"""旧应用表在业务库中的首次建表与统一升级；MySQL 用专用随机库验证结构。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from backend.database import make_engine, metadata
from backend.legacy_migrations.bootstrap import bootstrap_application_tables
from backend.manage import migration_head, schema_head, upgrade_unified
from backend.modules.reconciliation.group_entity import bindings
from backend.tests.test_business_migrations import migrated_engine as migrated_engine
from backend.tests.test_related_purchase_storage import sample as sample
from sqlalchemy import inspect, select, text


def test_bootstrap_preserves_preexisting_group_mapping(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'bootstrap.sqlite'}")
    try:
        bindings.create(engine)
        with engine.begin() as connection:
            connection.execute(
                bindings.insert(),
                {
                    "owner": "owner",
                    "account": "ns-a",
                    "supplier_id": "supplier",
                    "supplier_key": "key",
                    "supplier_name": "供应商",
                    "group_name": "开票群",
                    "chat_id": "group",
                    "employee": "负责人",
                    "userid": "user",
                    "enabled": True,
                    "revision": 1,
                    "updated_at": 1,
                },
            )
        assert bootstrap_application_tables(engine)
        with engine.connect() as connection:
            assert connection.execute(select(bindings.c.group_name)).scalar_one() == "开票群"
            assert set(metadata.tables) <= set(inspect(connection).get_table_names())
    finally:
        engine.dispose()


def test_bootstrap_rejects_untracked_history_and_mismatched_group_schema(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'unexpected.sqlite'}")
    try:
        metadata.tables["finance_review_snapshots"].create(engine)
        with pytest.raises(RuntimeError, match="未登记"):
            bootstrap_application_tables(engine)
    finally:
        engine.dispose()
    engine = make_engine(f"sqlite:///{tmp_path / 'mismatch.sqlite'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE finance_supplier_groups (owner TEXT PRIMARY KEY)"))
        with pytest.raises(RuntimeError, match="不一致"):
            bootstrap_application_tables(engine)
        assert "finance_invoice_tasks" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_mysql_unified_upgrade_keeps_business_tables_and_existing_group(context, migrated_engine):
    # migrated_engine只来自测试生成的随机库，不能将现有业务库作为测试目标。
    engine = migrated_engine
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE deployment_probe (id BIGINT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO deployment_probe VALUES (7)"))
    bindings.create(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE finance_supplier_groups COMMENT='已有群表中文说明'"))
        connection.execute(
            text(
                "ALTER TABLE finance_supplier_groups MODIFY owner "
                "VARCHAR(200) COLLATE utf8mb4_bin NOT NULL COMMENT '已有身份说明'"
            )
        )
    upgrade_unified(engine.url.render_as_string(hide_password=False))
    upgrade_unified(engine.url.render_as_string(hide_password=False))
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM deployment_probe")).scalar_one() == 7
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == migration_head()
        )
        assert "business_alembic_version" in inspect(connection).get_table_names()
        # 新迁移链在同一库中升级到最新，旧表保持不变。
        assert (
            connection.execute(text("SELECT version_num FROM schema_version")).scalar_one() == schema_head()
        )
        assert "source_purchase_order_lines" in inspect(connection).get_table_names()


def test_mysql_same_database_review_blocks_sync_and_keeps_single_commit(
    context, migrated_engine, sample, monkeypatch
):
    from backend.core.errors import ApiError
    from backend.modules.business.public import CustomsReconciliationSource
    from backend.modules.business.storage_service import StorageService
    from backend.modules.reconciliation import service as review_module
    from backend.modules.reconciliation.dto import ApproveRequest, DeclarationListQuery
    from backend.modules.reconciliation.service import ReconciliationService

    engine = migrated_engine
    upgrade_unified(engine.url.render_as_string(hide_password=False))
    ns, bundle = sample
    owner = f"user:{context.settings.admin_user}"
    storage = StorageService(ns, engine)
    storage.save_related_snapshot(bundle, owner)
    service = ReconciliationService(context.settings, None, engine, CustomsReconciliationSource(engine))
    query = DeclarationListQuery(keyword="CD70", account=ns.settings.account)
    preview = service.browse(query, owner).groups[0]
    entered, release = Event(), Event()
    audit = review_module.record_finance_review

    def pause(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return audit(*args, **kwargs)

    monkeypatch.setattr(review_module, "record_finance_review", pause)
    request = ApproveRequest(snapshotId=preview.snapshotId, note="同库审核")
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(service.approve, request, owner)
        try:
            assert entered.wait(timeout=10)
            with pytest.raises(ApiError) as busy:
                storage.save_related_snapshot(bundle, owner)
            assert busy.value.status == 409
            with pytest.raises(ApiError) as busy:
                service.approve(request, owner)
            assert busy.value.status == 409
        finally:
            release.set()
        result = job.result(timeout=10)
    retry = service.approve(request, owner)
    assert result.invoiceTaskCount == retry.invoiceTaskCount > 0
    assert retry.review.status == "approved"
