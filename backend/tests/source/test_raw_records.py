"""最新快照按来源身份和主键选择，不以正文内容或获取时间排序。"""

from datetime import datetime, timedelta

from backend.modules.source.dao import raw_record_dao
from backend.tests.test_source_storage import engine as engine


def seed_large_history(connection):
    now = datetime(2026, 11, 10)
    for version in range(3):
        payload = {"version": version, "evidence": "合成关联依据" * 40000}
        raw_record_dao.save(
            connection, "prod", "relation_evidence", "990", payload, now - timedelta(days=version)
        )
    # 接近业务表的来源分布，促使 MySQL 使用来源身份索引，覆盖 filesort 路径；
    # 只有三行时优化器可能直接倒扫主键，使旧查询也碰巧通过。
    for identity in range(1000, 1100):
        raw_record_dao.save(connection, "prod", "relation_evidence", str(identity), {"other": True}, now)
    return payload


def test_latest_snapshot_selects_newest_id_with_large_json_and_isolates_sources(engine):
    now = datetime(2026, 11, 10)
    with engine.begin() as connection:
        assert raw_record_dao.latest(connection, "prod", "relation_evidence", "990") is None
        expected = seed_large_history(connection)
        for account, kind, identity in (
            ("sandbox", "relation_evidence", "990"),
            ("prod", "customrecord_swc_declare_record", "990"),
            ("prod", "relation_evidence", "991"),
        ):
            raw_record_dao.save(connection, account, kind, identity, {"other": True}, now)
        assert raw_record_dao.latest(connection, "prod", "relation_evidence", "990") == expected
        assert raw_record_dao.latest(connection, "prod", "relation_evidence", "missing") is None
