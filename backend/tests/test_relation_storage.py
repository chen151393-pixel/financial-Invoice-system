"""独立关系表：历史迁移无损、外键隔离及幂等更新。"""

from datetime import datetime

import pytest
from backend.core.errors import ApiError
from backend.modules.business import relation_dao
from backend.modules.business.entity import load_tables
from backend.modules.business.relation_entity import RELATION_TABLE
from backend.modules.business.relation_storage_mapper import relation_evidence, relation_values
from backend.tests.test_business_migrations import legacy_relations
from backend.tests.test_business_migrations import migrated_engine as migrated_engine
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def test_legacy_relations_migrate_without_losing_evidence_or_amounts(migrated_engine):
    with migrated_engine.connect() as connection:
        tables = load_tables(connection, include_relations=True)
        head_table, results = tables["customs_declarations"], tables[RELATION_TABLE]
        for identity, original in legacy_relations().items():
            head = connection.execute(select(head_table).where(head_table.c.id == identity)).mappings().one()
            result = (
                connection.execute(select(results).where(results.c.customs_declaration_id == identity))
                .mappings()
                .one()
            )
            assert head["source_data"] == {"original": "保留原始数据"}
            assert head["synced_at"] == head["last_complete_sync_at"] == datetime(2026, 9, 1, 1, 2, 3, 123456)
            restored = relation_evidence(result, head["ns_internal_id"])
            # UTC两种ISO写法归一化；字段值、原始数组和金额精度必须保留。
            if "comparison" in original:
                original["comparison"]["readCompletedAt"] = "2026-09-01T01:02:03.654321+00:00"
            assert restored == original
            assert result["raw_line_count"] == result["packing_line_count"] == 1
            assert bool(result["review_ready"]) == (identity == 90001)


@pytest.mark.parametrize(
    "field,value",
    [("tenant_id", "other-owner"), ("ns_account", "other-account"), ("customs_declaration_id", 999999)],
)
def test_relation_foreign_key_rejects_cross_scope(migrated_engine, field, value):
    with migrated_engine.connect() as connection:
        tables = load_tables(connection, include_relations=True)
        head_table, results = tables["customs_declarations"], tables[RELATION_TABLE]
        head = connection.execute(select(head_table).where(head_table.c.id == 90001)).mappings().one()
        values = relation_values(head, legacy_relations()[90001])
        values[field] = value
        with pytest.raises(IntegrityError):
            relation_dao.save_result(connection, results, values)
        connection.rollback()


def test_repeat_update_keeps_identity_and_rollback_preserves_current_result(migrated_engine):
    with migrated_engine.connect() as connection:
        tables = load_tables(connection, include_relations=True)
        heads, results = tables["customs_declarations"], tables[RELATION_TABLE]
        query = select(results).where(results.c.customs_declaration_id == 90001)
        head = connection.execute(select(heads).where(heads.c.id == 90001)).mappings().one()
        before = dict(connection.execute(query).mappings().one())
        connection.rollback()
        with pytest.raises(ApiError):
            with connection.begin():
                values = relation_values(head, None)
                relation_dao.save_result(connection, results, values)
                relation_dao.save_result(connection, results, values)
                changed = connection.execute(query).mappings().one()
                assert changed["id"] == before["id"] and changed["created_at"] == before["created_at"]
                assert not changed["review_ready"] and changed["comparison_payload"] is None
                assert (
                    connection.execute(
                        select(results.c.id).where(
                            results.c.comparison_payload.is_(None), results.c.id == before["id"]
                        )
                    ).scalar_one()
                    == before["id"]
                )
                raise ApiError(409, "故障注入")
        assert dict(connection.execute(query).mappings().one()) == before
