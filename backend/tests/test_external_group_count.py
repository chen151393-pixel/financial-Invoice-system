"""群人数为可选展示字段，不影响预览、绑定及目录持久化。"""

import pytest
from backend.modules.task.dto.group_import_dto import CatalogQuery, ImportConfirm, PreviewQuery
from backend.tests.test_external_groups import USER, file, row, selection
from backend.tests.test_external_groups import engine as engine
from backend.tests.test_external_groups import ns as ns
from backend.tests.test_external_groups import services as services
from backend.tests.test_external_groups import setup as setup


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("", None),
        ("2*", None),
        ("未知", None),
        (-1, None),
        (2.5, None),
        ("=2+2", None),
        ("#VALUE!", None),
        (10**20, None),
        (0, 0),
        (8, 8),
        ("8", 8),
        ("8人", 8),
        ("8.0", 8),
        (100001, 100001),
    ],
)
def test_optional_count_import_binding_and_catalog(services, value, expected):
    preview, importer, catalog, _, supplier = services
    data = row()
    data[1], data[4] = value, "未获取"
    receipt = preview.create(file([data]), USER)
    assert receipt.valid == 1 and receipt.invalid == 0 and receipt.matched == 1
    item = preview.browse(PreviewQuery(importId=receipt.importId), USER).items[0]
    assert item.group.memberCount == expected and item.group.createdAt == ""
    result = importer.confirm(
        ImportConfirm(importId=receipt.importId, selections=[selection(supplier)]), USER
    )
    assert result.imported == 1 and result.bound == 1
    saved = catalog.browse(CatalogQuery(), USER).items[0]
    assert saved.memberCount == expected and saved.suppliers[0].supplierId == supplier.supplierId
