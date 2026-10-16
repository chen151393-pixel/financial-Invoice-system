"""同一持久预览并发确认只执行一次，必须在专用 MySQL 验证。"""

from backend.modules.task.dto.group_import_dto import CatalogQuery, ImportConfirm
from backend.modules.task.dto.supplier_group_dto import SupplierProfileQuery
from backend.tests.test_external_groups import file, row, selection
from backend.tests.test_external_groups import services as services
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_matching_mysql import race
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_supplier_profiles import USER
from backend.tests.test_supplier_profiles import setup as setup


def test_concurrent_confirm_is_idempotent(services):
    preview, importer, catalog, profiles, supplier = services
    item = preview.create(file([row()]), USER)
    request = ImportConfirm(importId=item.importId, selections=[selection(supplier)])
    assert race(lambda: importer.confirm(request, USER), lambda: importer.confirm(request, USER)) == [
        "ok",
        "ok",
    ]
    assert catalog.browse(CatalogQuery(), USER).total == 1
    assert profiles.browse(SupplierProfileQuery(keyword="江川"), USER).items[0].binding.revision == 1
