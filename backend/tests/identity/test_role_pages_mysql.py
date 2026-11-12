"""只在专用随机 MySQL 库验证授权并发，不能用 SQLite 代替。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.modules.identity.dao import role_page_dao
from backend.modules.identity.service.role_page_service import RolePageService
from backend.modules.identity.service.session_service import IdentityService
from backend.tests.test_matching_mysql import engine as engine


def test_concurrent_role_edit_keeps_one_revision(engine, env):
    identity = IdentityService(load_settings(env))
    service = RolePageService(engine, identity)
    barrier = Barrier(2)

    def save(pages):
        barrier.wait(timeout=10)
        try:
            return 200, service.save("finance", pages, 0, "user:admin").pages
        except ApiError as error:
            return error.status, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [["finance"], ["invoices"]]))
    assert sorted(code for code, _ in results) == [200, 409]
    with engine.connect() as connection:
        row = role_page_dao.configurations(connection)["finance"]
    assert row["revision"] == 1
    assert row["pages"] == next(pages for code, pages in results if code == 200)
