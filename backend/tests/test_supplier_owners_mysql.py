"""专用 MySQL 多连接验证同一预览的并发保存只成功一次，SQLite 不代替并发验收。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from backend.core.errors import ApiError
from backend.modules.task.dao import supplier_owner_dao
from backend.modules.task.dto.supplier_owner_dto import OwnerSave
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_supplier_owners import ACTOR, change
from backend.tests.test_supplier_owners import setup as setup


def test_concurrent_saves_of_same_preview_keep_single_history_version(engine, setup):
    service, rows = setup
    body = change(rows)
    preview = service.preview(body, ACTOR)
    saved = OwnerSave(**body.model_dump(), previewToken=preview.previewToken)
    barrier = Barrier(2)

    def commit(_):
        barrier.wait(timeout=10)
        try:
            service.save(saved, ACTOR)
            return 200
        except ApiError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(commit, range(2)))
    assert sorted(statuses) == [200, 409]
    with engine.connect() as connection:
        records = supplier_owner_dao.records(connection)
        assert len(records) == len(rows)
        assert len({(row["supplier_id"], row["company_id"]) for row in records}) == len(rows)
