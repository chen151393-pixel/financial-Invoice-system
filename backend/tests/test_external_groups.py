"""外部群导入的真实事务、持久预览、手动关联与失败保护（隔离 SQLite）。"""

import base64
from datetime import UTC, datetime
from io import BytesIO

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.task.dto.group_import_dto import (
    CatalogBinding,
    CatalogQuery,
    GroupImportFile,
    ImportConfirm,
    ImportSelection,
    PreviewQuery,
)
from backend.modules.task.dto.supplier_group_dto import SupplierProfileQuery
from backend.modules.task.service.external_group_service import ExternalGroupService
from backend.modules.task.service.group_import_preview import GroupImportPreview
from backend.modules.task.service.group_import_service import GroupImportService
from backend.modules.task.service.group_xlsx_reader import HEADERS, read_groups
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_supplier_profiles import NAME, USER
from backend.tests.test_supplier_profiles import setup as setup
from fastapi.testclient import TestClient
from openpyxl import Workbook


def file(rows, headers=None):
    book = Workbook()
    book.active.append(headers or HEADERS)
    for row in rows:
        book.active.append(row)
    raw = BytesIO()
    book.save(raw)
    return GroupImportFile(filename="外部群.xlsx", content=base64.b64encode(raw.getvalue()).decode())


def row(name=NAME, chat="wr_example", owner="Owner1"):
    return [name, 8, "群主甲", "供应链/采购组", "2026-10-16 12:36", chat, owner]


@pytest.fixture
def services(engine, setup):
    groups, profiles, supplier, _ = setup
    return (
        GroupImportPreview(engine, groups.directory),
        GroupImportService(engine, groups.directory),
        ExternalGroupService(engine, groups.directory),
        profiles,
        supplier,
    )


def selection(supplier, **extra):
    return ImportSelection(rowNo=2, supplierId=supplier.supplierId, revision=0, **extra)


def test_preview_is_not_import_and_confirm_is_persistent_idempotent(services):
    preview, importer, catalog, profiles, supplier = services
    receipt = preview.create(file([row(), row("群聊", "wr_other")]), USER)
    assert receipt.valid == 2 and receipt.matched == 1 and receipt.unmatched == 1
    assert catalog.browse(CatalogQuery(), USER).total == 0
    assert profiles.browse(SupplierProfileQuery(status="unbound"), USER).total == 2
    page = preview.browse(PreviewQuery(importId=receipt.importId), USER)
    assert page.items[0].candidates[0].supplierId == supplier.supplierId
    assert len(page.suggestions) == 1 and page.suggestions[0].rowNo == 2
    body = ImportConfirm(importId=receipt.importId, selections=[selection(supplier)])
    result = importer.confirm(body, USER)
    assert (result.imported, result.bound) == (2, 1)
    assert GroupImportService(importer.engine, importer.directory).confirm(body, USER) == result
    assert profiles.browse(SupplierProfileQuery(keyword="江川"), USER).items[0].binding.revision == 1
    assert catalog.browse(CatalogQuery(status="unbound"), USER).total == 1
    assert preview.browse(PreviewQuery(importId=receipt.importId), USER).status == "confirmed"
    with pytest.raises(ApiError, match="不同关联"):
        importer.confirm(ImportConfirm(importId=receipt.importId), USER)


def test_manual_association_and_replace_require_version_and_explicit_confirmation(services):
    preview, importer, catalog, profiles, supplier = services
    receipt = preview.create(file([row("简称对接群")]), USER)
    importer.confirm(ImportConfirm(importId=receipt.importId), USER)
    group = catalog.browse(CatalogQuery(), USER).items[0]
    body = CatalogBinding(
        chatId=group.chatId, catalogRevision=group.revision, supplierId=supplier.supplierId, revision=0
    )
    saved = catalog.associate(body, USER)
    assert saved.employee == "群主甲" and saved.userid == "Owner1"
    with pytest.raises(ApiError, match="已被修改"):
        catalog.associate(body, USER)
    other = preview.create(file([row("新群", "wr_new")]), USER)
    with pytest.raises(ApiError, match="明确确认替换"):
        importer.confirm(
            ImportConfirm(
                importId=other.importId,
                selections=[ImportSelection(rowNo=2, supplierId=supplier.supplierId, revision=1)],
            ),
            USER,
        )
    assert catalog.browse(CatalogQuery(), USER).total == 1  # 目录写入随绑定失败一起回滚。
    importer.confirm(
        ImportConfirm(
            importId=other.importId,
            selections=[
                ImportSelection(rowNo=2, supplierId=supplier.supplierId, revision=1, replaceExisting=True)
            ],
        ),
        USER,
    )
    assert profiles.browse(SupplierProfileQuery(keyword="江川"), USER).items[0].binding.chatId == "wr_new"


def test_import_does_not_silently_update_old_bindings_and_stale_catalog_rejected(services):
    preview, importer, catalog, profiles, supplier = services
    first = preview.create(file([row()]), USER)
    stale = preview.create(file([row()]), USER)
    importer.confirm(ImportConfirm(importId=first.importId, selections=[selection(supplier)]), USER)
    with pytest.raises(ApiError, match="目录已更新"):
        importer.confirm(ImportConfirm(importId=stale.importId), USER)
    change = preview.create(file([row(owner="NewOwner")]), USER)
    importer.confirm(ImportConfirm(importId=change.importId), USER)
    group = catalog.browse(CatalogQuery(), USER).items[0]
    assert group.revision == 2 and group.userid == "NewOwner"
    assert profiles.browse(SupplierProfileQuery(keyword="江川"), USER).items[0].binding.userid == "Owner1"
    with pytest.raises(ApiError, match="目录已更新"):
        catalog.associate(
            CatalogBinding(
                chatId=group.chatId, catalogRevision=1, supplierId=supplier.supplierId, revision=1
            ),
            USER,
        )


def test_excel_validation_formulas_missing_ids_duplicates_and_beijing_dates():
    bad = row()
    bad[5] = None
    formula = row(chat="formula")
    formula[0] = "=1+1"
    number = row(chat="number")
    number[5] = 12345678901234567
    rows = read_groups(
        file([row(), row(chat="WR_example"), bad, formula, number, row(chat="dup"), row(chat="dup")])
    )
    assert not rows[0]["issue"] and not rows[1]["issue"]  # ID 区分大小写。
    assert all(r["issue"] for r in rows[2:])
    assert datetime.fromisoformat(rows[0]["group"]["createdAt"]) == datetime(2026, 10, 16, 4, 36, tzinfo=UTC)
    with pytest.raises(ApiError, match="补齐两列"):
        read_groups(file([row()[:5]], HEADERS[:5]))
    with pytest.raises(ApiError, match="无法读取"):
        read_groups(GroupImportFile(filename="bad.xlsx", content="invalid"))
    with pytest.raises(ApiError, match="1000"):
        read_groups(file([row(chat=str(i)) for i in range(1001)]))


def test_partial_invalid_rows_and_identity_permissions(services):
    preview, importer, catalog, _, supplier = services
    bad = row(chat="bad")
    bad[5] = None
    receipt = preview.create(file([row(), bad]), USER)
    assert receipt.invalid == 1
    with pytest.raises(ApiError, match="不属于"):
        preview.browse(PreviewQuery(importId=receipt.importId), "user:other")
    with pytest.raises(ApiError, match="只读"):
        preview.create(file([row()]), "service:test")
    with pytest.raises(ApiError, match="只读"):
        importer.confirm(ImportConfirm(importId=receipt.importId), "service:test")
    with pytest.raises(ApiError, match="错误行"):
        importer.confirm(
            ImportConfirm(
                importId=receipt.importId,
                selections=[ImportSelection(rowNo=3, supplierId=supplier.supplierId, revision=0)],
            ),
            USER,
        )
    result = importer.confirm(ImportConfirm(importId=receipt.importId), USER)
    assert result.imported == 1 and result.skipped == 1
    assert catalog.browse(CatalogQuery(keyword="%"), USER).total == 0


def test_duplicate_supplier_choice_rejected_and_catalog_pagination(services):
    preview, importer, catalog, _, supplier = services
    receipt = preview.create(file([row(chat=f"wr_{i}") for i in range(22)]), USER)
    assert len(preview.browse(PreviewQuery(importId=receipt.importId), USER).items) == 20
    assert not preview.browse(PreviewQuery(importId=receipt.importId), USER).suggestions
    with pytest.raises(ApiError, match="一个供应商"):
        importer.confirm(
            ImportConfirm(
                importId=receipt.importId,
                selections=[
                    selection(supplier),
                    ImportSelection(rowNo=3, supplierId=supplier.supplierId, revision=0),
                ],
            ),
            USER,
        )
    importer.confirm(ImportConfirm(importId=receipt.importId), USER)
    page = catalog.browse(CatalogQuery(page=2), USER)
    assert page.total == 22 and len(page.items) == 2


def test_expired_preview_and_missing_supplier(services, engine):
    from backend.modules.task.entity.group_import import group_imports
    from sqlalchemy import update

    preview, importer, _, _, _ = services
    receipt = preview.create(file([row()]), USER)
    with pytest.raises(ApiError, match="不存在"):
        importer.confirm(
            ImportConfirm(
                importId=receipt.importId,
                selections=[ImportSelection(rowNo=2, supplierId="999999", revision=0)],
            ),
            USER,
        )
    with engine.begin() as connection:
        connection.execute(update(group_imports).values(created_at=datetime(2000, 1, 1)))
    with pytest.raises(ApiError, match="24 小时"):
        importer.confirm(ImportConfirm(importId=receipt.importId), USER)


def test_http_upload_preview_confirm_and_manual_catalog(context, engine, setup):
    app = create_app(context.settings, context.ns, engine)
    root = "/api/tasks/external-groups"
    headers = {"Origin": context.settings.origin}
    with TestClient(app) as client:
        assert client.post(root + "/query", json={}).status_code == 401
        client.post(
            "/api/session",
            headers=headers,
            json={"username": "admin", "password": context.settings.admin_password},
        )
        result = client.post(root + "/import/preview", headers=headers, json=file([row()]).model_dump())
        assert result.status_code == 200, result.text
        import_id = result.json()["importId"]
        result = client.post(root + "/import/query", headers=headers, json={"importId": import_id})
        assert result.status_code == 200 and result.json()["items"][0]["group"]["chatId"] == "wr_example"
        assert (
            client.post(root + "/import/confirm", headers=headers, json={"importId": import_id}).status_code
            == 200
        )
        assert client.post(root + "/query", headers=headers, json={}).json()["total"] == 1
        assert (
            client.post(
                root + "/associate",
                headers=headers,
                json={
                    "chatId": "wr_example",
                    "catalogRevision": 1,
                    "supplierId": setup[2].supplierId,
                    "revision": 0,
                    "employee": "伪造",
                },
            ).status_code
            == 400
        )


@pytest.mark.parametrize(
    "created", [None, "", "随意填写", "2026年10月16日", 123, "=NOW()", "#VALUE!", "0001-03-01"]
)
def test_optional_creation_time_does_not_block_preview_binding_or_catalog(services, created):
    preview, importer, catalog, profiles, supplier = services
    data = row()
    data[4] = created
    receipt = preview.create(file([data]), USER)
    assert receipt.valid == 1 and receipt.invalid == 0 and receipt.matched == 1
    page = preview.browse(PreviewQuery(importId=receipt.importId), USER)
    assert page.items[0].group.createdAt == ""
    result = importer.confirm(
        ImportConfirm(importId=receipt.importId, selections=[selection(supplier)]), USER
    )
    assert result.imported == 1 and result.bound == 1
    assert catalog.browse(CatalogQuery(), USER).items[0].createdAt == ""
    assert profiles.browse(SupplierProfileQuery(keyword="江川"), USER).items[0].binding.chatId == "wr_example"
