"""只在新建隔离 MySQL 库验证母采购迁移和外键，不向真实业务库插入测试数据。"""

import json
import os
import re
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from backend.manage import upgrade_business
from backend.modules.business.storage_service import StorageService
from backend.modules.source.policy.relation_policy import source_digest
from backend.tests.test_pl_storage import configured_ns
from backend.tests.test_reconciliation import source_result
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError

ROOT = Path(__file__).resolve().parents[2]


def test_business_migration_offline_is_additive(capsys):
    upgrade_business("mysql+pymysql://unused@localhost/unused", sql=True)
    sql = capsys.readouterr().out
    assert "CREATE TABLE customs_reconciliation_results" in sql

    assert "CREATE TABLE invoice_purchase_link_batches" in sql
    assert "CREATE TABLE invoice_purchase_link_pairs" in sql
    assert "fk_customs_reconciliation_parent" in sql
    assert "CREATE TABLE parent_purchase_orders" in sql
    assert "CREATE TABLE parent_purchase_order_lines" in sql
    assert "business_alembic_version" in sql
    assert "fk_purchase_line_parent_header" in sql
    assert "fk_purchase_line_parent_line" in sql
    assert "ck_purchase_parent_relation" in sql
    assert "ns_parent_line_ref" in sql
    assert "ALTER TABLE invoices" not in sql
    assert "ALTER TABLE customs_declarations" not in sql
    assert not re.search(r"(?m)^\s*(DROP|DELETE|TRUNCATE)\b", sql)


def test_business_migration_requires_explicit_mysql_target():
    with pytest.raises(ValueError, match="MySQL"):
        upgrade_business("")
    with pytest.raises(RuntimeError, match="MySQL"):
        upgrade_business("sqlite:///:memory:")


def legacy_relations():
    payload = {"version": 3, "group": source_result("ns-a")["groups"][0]}
    base = {
        "version": 1,
        "account": "ns-a",
        "declarationId": "101",
        "status": "matched",
        "mode": "full_sync",
        "readAt": "2026-09-01T01:02:03.123456+00:00",
        "issues": [],
        "rawLines": [{"quantity": "9007199254740993.000000000000000001"}],
        "packingLines": [{"id": "80"}],
        "purchaseLinks": [],
        "parentLines": [],
        "comparison": {
            "payload": payload,
            "digest": source_digest(payload),
            "ready": True,
            "reason": "",
            "requestId": "legacy-request",
            "readCompletedAt": "2026-09-01T01:02:03.654321Z",
        },
    }
    partial = {
        **base,
        "declarationId": "102",
        "status": "partial",
        "mode": "evidence_backfill",
        "issues": ["原始行缺失"],
    }
    partial.pop("comparison")
    return {90001: base, 90002: partial}


@pytest.fixture(scope="module")
def migrated_engine():
    server_url = os.environ.get("BUSINESS_MIGRATION_TEST_SERVER_URL")
    if not server_url:
        pytest.skip("未提供专用MySQL建库连接，未执行真实外键验证")
    url = make_url(server_url)
    if url.drivername != "mysql+pymysql":
        pytest.fail("迁移集成测试必须使用MySQL")
    # 库名完全由测试生成，销毁时只使用本次生成的标识，不接受外部目标库名。
    database = "codex_" + uuid4().hex + "_parents_test"
    server = create_engine(url.set(database=None))
    engine = None
    created = False
    try:
        with server.connect() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
            )
            created = True
        engine = create_engine(url.set(database=database))
        with engine.begin() as connection:
            for file in ("business-schema.sql", "invoice-excel-design.sql"):
                sql = (ROOT / "docs" / "mysql" / file).read_text(encoding="utf-8")
                sql = re.sub(r"(?m)^--.*$", "", sql)
                for statement in sql.split(";"):
                    statement = statement.strip()
                    if statement and not statement.startswith(("CREATE DATABASE", "USE ")):
                        connection.execute(text(statement))
            connection.execute(text("CREATE TABLE unit_dictionary (id BIGINT PRIMARY KEY)"))
            connection.execute(text("INSERT INTO unit_dictionary VALUES (7)"))
            connection.execute(
                text(
                    "INSERT INTO purchase_orders (id,tenant_id,ns_account,ns_internal_id,order_no,parent_order_no,source_data) VALUES (1,'a','ns-a','old-child','旧子单','旧母单名称','{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO purchase_order_lines (id,tenant_id,purchase_order_id,source_line_key,amount) VALUES (1,'a',1,'old-line',123.456789)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO invoices (id,tenant_id,external_system,external_account,external_record_id,source_data,invoice_no) VALUES (1,'a','excel','test','invoice-1','{}','12345678901234567890')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO invoice_lines (id,tenant_id,invoice_id,source_line_key,quantity) VALUES (1,'a',1,'invoice-line',29.24937028)"
                )
            )
        config = Config(str(ROOT / "backend" / "legacy_migrations" / "business.ini"))
        config.attributes["database_url"] = engine.url.render_as_string(hide_password=False)
        command.upgrade(config, "0001_business_parents")
        # 模拟上一版本已有关联的数据，验证增量升级保留外键并正确回填状态。
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO parent_purchase_orders (id,tenant_id,ns_account,ns_record_type,ns_internal_id,source_data) VALUES (20,'a','ns-a','purchaseOrder','old-parent','{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO parent_purchase_order_lines (id,tenant_id,parent_purchase_order_id,source_line_key,source_data) VALUES (200,'a',20,'old-parent-line','{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO purchase_orders (id,tenant_id,ns_account,ns_internal_id,source_data,parent_purchase_order_id) VALUES (2,'a','ns-a','old-linked-child','{}',20)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO purchase_order_lines (id,tenant_id,purchase_order_id,source_line_key,parent_purchase_order_id,parent_purchase_order_line_id) VALUES (2,'a',2,'old-linked-line',20,200)"
                )
            )
        # 旧版关系存在单头JSON；覆盖仅补依据和完整v3结果两种历史来源。
        with engine.begin() as connection:
            for identity, evidence in legacy_relations().items():
                connection.execute(
                    text(
                        "INSERT INTO customs_declarations (id,tenant_id,ns_account,ns_internal_id,record_no,source_data,synced_at,last_complete_sync_at) "
                        "VALUES (:id,'legacy-owner','ns-a',:ns_id,:record_no,:source,'2026-09-01 01:02:03.123456','2026-09-01 01:02:03.123456')"
                    ),
                    {
                        "id": identity,
                        "ns_id": evidence["declarationId"],
                        "record_no": "CDTEST001",
                        "source": json.dumps(
                            {"original": "保留原始数据", "relationEvidence": evidence}, ensure_ascii=False
                        ),
                    },
                )
        upgrade_business(engine.url.render_as_string(hide_password=False))
        # 版本登记后的再次执行应无DDL，不重建两表也不清除已有数据。
        upgrade_business(engine.url.render_as_string(hide_password=False))
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with server.connect() as connection:
                connection.execute(text(f"DROP DATABASE `{database}`"))
        server.dispose()


def test_migration_preserves_existing_data_and_unrelated_tables(migrated_engine):
    with migrated_engine.connect() as c:
        assert (
            c.execute(text("SELECT version_num FROM business_alembic_version")).scalar_one()
            == "0005_customs_relations"
        )
        row = c.execute(
            text(
                "SELECT parent_order_no,parent_purchase_order_id,parent_relation_status FROM purchase_orders WHERE id=1"
            )
        ).one()
        assert row == ("旧母单名称", None, "unknown")
        assert c.execute(
            text("SELECT parent_purchase_order_id,parent_relation_status FROM purchase_orders WHERE id=2")
        ).one() == (20, "linked")
        assert c.execute(
            text(
                "SELECT parent_purchase_order_id,parent_purchase_order_line_id,ns_parent_line_ref FROM purchase_order_lines WHERE id=2"
            )
        ).one() == (20, 200, None)
        assert (
            str(c.execute(text("SELECT amount FROM purchase_order_lines WHERE id=1")).scalar_one())
            == "123.456789"
        )
        assert (
            str(c.execute(text("SELECT quantity FROM invoice_lines WHERE id=1")).scalar_one())
            == "29.24937028"
        )
        assert (
            c.execute(text("SELECT invoice_no FROM invoices WHERE id=1")).scalar_one()
            == "12345678901234567890"
        )
        assert c.execute(text("SELECT id FROM unit_dictionary")).scalar_one() == 7
        assert "alembic_version" not in inspect(c).get_table_names()


def test_customs_price_preserves_source_precision(migrated_engine):
    with migrated_engine.connect() as connection:
        column = next(
            row
            for row in inspect(connection).get_columns("customs_declaration_lines")
            if row["name"] == "unit_price"
        )
        assert (column["type"].precision, column["type"].scale) == (38, 18)
        connection.execute(
            text(
                "INSERT INTO customs_declarations (id,tenant_id,ns_account,ns_internal_id,source_data) VALUES (90871,'precision','ns-a','precision','{}')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO customs_declaration_lines (id,tenant_id,customs_declaration_id,source_line_key,unit_price) VALUES (90871,'precision',90871,'precision',:price)"
            ),
            {"price": Decimal("1.4152906944825692")},
        )
        value = connection.execute(
            text("SELECT unit_price FROM customs_declaration_lines WHERE id=90871")
        ).scalar_one()
        assert value == Decimal("1.4152906944825692")
        connection.rollback()


@pytest.fixture
def linked(migrated_engine):
    with migrated_engine.connect() as c:
        transaction = c.begin()
        try:
            c.execute(
                text(
                    "INSERT INTO parent_purchase_orders (id,tenant_id,ns_account,ns_record_type,ns_internal_id,source_data) VALUES (10,'a','ns-a','purchaseOrder','10','{}'),(11,'a','ns-a','purchaseOrder','11','{}'),(12,'b','ns-b','purchaseOrder','10','{}')"
                )
            )
            c.execute(
                text(
                    "INSERT INTO parent_purchase_order_lines (id,tenant_id,parent_purchase_order_id,source_line_key,source_data) VALUES (100,'a',10,'line-1','{}'),(101,'a',11,'line-1','{}')"
                )
            )
            c.execute(
                text(
                    "UPDATE purchase_orders SET parent_purchase_order_id=10,parent_relation_status='linked' WHERE id=1"
                )
            )
            yield c
        finally:
            transaction.rollback()


def test_valid_parent_header_and_line_relationship(linked):
    linked.execute(
        text(
            "UPDATE purchase_order_lines SET parent_purchase_order_id=10,parent_purchase_order_line_id=100 WHERE id=1"
        )
    )
    assert (
        linked.execute(
            text("SELECT parent_purchase_order_line_id FROM purchase_order_lines WHERE id=1")
        ).scalar_one()
        == 100
    )
    with pytest.raises(IntegrityError):
        linked.execute(text("UPDATE purchase_orders SET parent_purchase_order_id=11 WHERE id=1"))
    with pytest.raises(IntegrityError):
        linked.execute(text("DELETE FROM parent_purchase_orders WHERE id=10"))


@pytest.mark.parametrize("tenant,account,parent", [("a", "ns-b", 10), ("b", "ns-a", 10), ("a", "ns-a", 999)])
def test_reject_cross_scope_or_missing_parent(linked, tenant, account, parent):
    with pytest.raises(IntegrityError):
        linked.execute(
            text(
                "INSERT INTO purchase_orders (tenant_id,ns_account,ns_internal_id,source_data,parent_purchase_order_id,parent_relation_status) VALUES (:tenant,:account,'new-child','{}',:parent,'linked')"
            ),
            {"tenant": tenant, "account": account, "parent": parent},
        )


@pytest.mark.parametrize("parent,line", [(10, 101), (11, 101), (10, None), (None, 100), (10, 999)])
def test_reject_mismatched_or_partial_parent_line(linked, parent, line):
    error_type = OperationalError if parent is None or line is None else IntegrityError
    with pytest.raises(error_type) as error:
        linked.execute(
            text(
                "UPDATE purchase_order_lines SET parent_purchase_order_id=:parent,parent_purchase_order_line_id=:line WHERE id=1"
            ),
            {"parent": parent, "line": line},
        )
    assert error.value.orig.args[0] == (3819 if error_type is OperationalError else 1452)


def test_parent_source_and_line_uniqueness(linked):
    with pytest.raises(IntegrityError):
        linked.execute(
            text(
                "INSERT INTO parent_purchase_orders (tenant_id,ns_account,ns_record_type,ns_internal_id,source_data) VALUES ('a','ns-a','purchaseOrder','10','{}')"
            )
        )
    with pytest.raises(IntegrityError):
        linked.execute(
            text(
                "INSERT INTO parent_purchase_order_lines (tenant_id,parent_purchase_order_id,source_line_key,source_data) VALUES ('a',10,'line-1','{}')"
            )
        )


def test_existing_invoice_and_customs_foreign_keys_remain(linked):
    with pytest.raises(IntegrityError):
        linked.execute(
            text(
                "INSERT INTO invoice_lines (tenant_id,invoice_id,source_line_key) VALUES ('b',1,'wrong-tenant')"
            )
        )
    with pytest.raises(IntegrityError):
        linked.execute(text("UPDATE purchase_orders SET customs_declaration_id=999 WHERE id=1"))


@pytest.mark.parametrize(
    "status,parent",
    [("unknown", 10), ("no_parent", 10), ("linked", None), ("other", None), ("LINKED", 10)],
)
def test_reject_inconsistent_parent_status(linked, status, parent):
    with pytest.raises(OperationalError) as error:
        linked.execute(
            text(
                "UPDATE purchase_orders SET parent_relation_status=:status,parent_purchase_order_id=:parent WHERE id=1"
            ),
            {"status": status, "parent": parent},
        )
    assert error.value.orig.args[0] == 3819


def test_parent_status_and_reference_change_together(linked):
    for status, parent in (("no_parent", None), ("unknown", None), ("linked", 10)):
        linked.execute(
            text(
                "UPDATE purchase_orders SET parent_relation_status=:status,parent_purchase_order_id=:parent WHERE id=1"
            ),
            {"status": status, "parent": parent},
        )
        assert linked.execute(
            text("SELECT parent_relation_status,parent_purchase_order_id FROM purchase_orders WHERE id=1")
        ).one() == (status, parent)


def test_default_status_does_not_claim_no_parent_or_accept_link(linked):
    linked.execute(
        text(
            "INSERT INTO purchase_orders (tenant_id,ns_account,ns_internal_id,source_data) VALUES ('a','ns-a','unknown-child','{}')"
        )
    )
    assert (
        linked.execute(
            text("SELECT parent_relation_status FROM purchase_orders WHERE ns_internal_id='unknown-child'")
        ).scalar_one()
        == "unknown"
    )
    with pytest.raises(OperationalError) as error:
        linked.execute(
            text(
                "INSERT INTO purchase_orders (tenant_id,ns_account,ns_internal_id,source_data,parent_purchase_order_id) VALUES ('a','ns-a','inconsistent-child','{}',10)"
            )
        )
    assert error.value.orig.args[0] == 3819


def test_raw_parent_line_ref_is_not_a_local_id(linked):
    for raw in ("0007", "0", "NS-line:AB-19", None):
        linked.execute(
            text("UPDATE purchase_order_lines SET ns_parent_line_ref=:raw WHERE id=1"), {"raw": raw}
        )
        assert linked.execute(
            text(
                "SELECT ns_parent_line_ref,parent_purchase_order_id,parent_purchase_order_line_id FROM purchase_order_lines WHERE id=1"
            )
        ).one() == (raw, None, None)


def test_existing_sync_preserves_relation_fields(migrated_engine):
    service = StorageService(configured_ns(), migrated_engine)
    owner = "migration-sync-" + uuid4().hex
    service.sync("PL001", owner)
    tenant, _ = service.scope(owner)
    with migrated_engine.begin() as c:
        states = (
            c.execute(
                text("SELECT parent_relation_status FROM purchase_orders WHERE tenant_id=:tenant"),
                {"tenant": tenant},
            )
            .scalars()
            .all()
        )
        assert states == ["unknown", "unknown"]
        c.execute(
            text("UPDATE purchase_orders SET parent_relation_status='no_parent' WHERE tenant_id=:tenant"),
            {"tenant": tenant},
        )
        c.execute(
            text("UPDATE purchase_order_lines SET ns_parent_line_ref='0007' WHERE tenant_id=:tenant"),
            {"tenant": tenant},
        )
    result = service.sync("PL001", owner)
    assert result["purchase"]["created"] == 0
    assert result["purchase"]["updated"] == 2
    with migrated_engine.connect() as c:
        assert c.execute(
            text("SELECT parent_relation_status FROM purchase_orders WHERE tenant_id=:tenant"),
            {"tenant": tenant},
        ).scalars().all() == ["no_parent", "no_parent"]
        assert c.execute(
            text("SELECT ns_parent_line_ref FROM purchase_order_lines WHERE tenant_id=:tenant"),
            {"tenant": tenant},
        ).scalars().all() == ["0007", "0007"]
