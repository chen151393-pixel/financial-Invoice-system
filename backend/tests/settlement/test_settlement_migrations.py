"""验证已有银行收汇数据沿结汇迁移链升级。"""

from alembic import command
from backend.manage import SCHEMA_INI, _config
from backend.tests.test_schema_baseline import insert
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import inspect, text

INITIAL_REVISION = "0047_settlement_bank_receipts"
IMPORT_REVISION = "0048_settlement_receipt_import"
ALLOCATION_REVISION = "0049_settlement_direct_allocations"


def test_upgrade_keeps_legacy_and_imported_bank_receipts(schema_engine):
    details = {
        "receipt_date": "2026-10-08",
        "receiving_company": "收款公司",
        "payer_name": "ACME LTD",
        "payer_key": "acme ltd",
        "customer_name": "ACME LTD",
        "customer_key": "acme ltd",
        "currency": "USD",
        "amount": "12.50",
        "imported_by": "finance-user",
        "imported_at": "2026-10-08 00:00:00",
    }
    with schema_engine.begin() as connection:
        insert(connection, "settlement_bank_receipts", reference="LEGACY", **details)

    cfg = _config(SCHEMA_INI, schema_engine.url.render_as_string(hide_password=False))
    command.upgrade(cfg, IMPORT_REVISION)
    with schema_engine.begin() as connection:
        schema = inspect(connection)
        assert not schema.has_table("settlement_direct_allocations")
        assert any(
            index["unique"] and index["column_names"] == ["import_key"]
            for index in schema.get_indexes("settlement_bank_receipts")
        )
        insert(
            connection,
            "settlement_bank_receipts",
            reference="IMPORTED",
            receipt_time="09:01:17",
            import_key="a" * 64,
            **details,
        )

    command.upgrade(cfg, ALLOCATION_REVISION)
    with schema_engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM schema_version")).scalar_one() == (
            ALLOCATION_REVISION
        )
        rows = connection.execute(
            text("SELECT reference, receipt_time, import_key FROM settlement_bank_receipts ORDER BY id")
        ).all()
        assert rows[0] == ("LEGACY", None, None)
        assert rows[1][0] == "IMPORTED"
        assert str(rows[1][1]).zfill(8) == "09:01:17"
        assert rows[1][2] == "a" * 64
        foreign_keys = inspect(connection).get_foreign_keys("settlement_direct_allocations")
        assert [(key["constrained_columns"], key["referred_table"]) for key in foreign_keys] == [
            (["receipt_id"], "settlement_bank_receipts")
        ]
