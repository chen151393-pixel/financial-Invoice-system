"""真实 MySQL 回归：大 JSON 快照的读取不依赖扩大排序缓冲区。"""

from backend.modules.source.dao import raw_record_dao
from backend.tests.source.test_raw_records import seed_large_history
from backend.tests.test_matching_mysql import engine as engine
from sqlalchemy import text


def test_latest_large_snapshot_with_small_mysql_sort_buffer(engine):
    with engine.begin() as connection:
        original = connection.execute(text("SELECT @@session.sort_buffer_size")).scalar_one()
        try:
            # 仅改变隔离测试连接；不改全局参数或业务库。
            connection.execute(text("SET SESSION sort_buffer_size = 32768"))
            expected = seed_large_history(connection)
            assert raw_record_dao.latest(connection, "prod", "relation_evidence", "990") == expected
        finally:
            connection.execute(text("SET SESSION sort_buffer_size = :size"), {"size": original})
