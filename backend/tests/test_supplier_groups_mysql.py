"""在独立随机 MySQL 应用库验证群配置的并发唯一性和版本保护。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from backend.core.errors import ApiError
from backend.modules.reconciliation.group_entity import bindings
from backend.modules.reconciliation.group_service import SupplierGroupService
from backend.tests.test_finance_list import OWNER
from backend.tests.test_reconciliation_mysql import mysql_finance_context as mysql_finance_context
from backend.tests.test_supplier_groups import FakeWecom, binding
from sqlalchemy import func, select


class Suppliers:
    def read(self, owner, **criteria):
        return {"items": [{"account": "prod", "supplierId": "vendor1", "supplierName": "隔离供应商"}]}


def test_mysql_concurrent_create_and_update(mysql_finance_context):
    service = SupplierGroupService(mysql_finance_context.engine, Suppliers(), OWNER, wecom=FakeWecom())
    for revision in (0, 1):
        barrier = Barrier(2)

        def save(index):
            barrier.wait(timeout=5)
            try:
                return service.save(
                    OWNER, binding(revision=revision, chatId=f"wr_{revision}_{index}")
                ).revision
            except ApiError as error:
                return error.status

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(save, [1, 2]))
        assert sorted(results) == [revision + 1, 409]
    with mysql_finance_context.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(bindings)) == 1
        assert connection.scalar(select(bindings.c.revision)) == 2
