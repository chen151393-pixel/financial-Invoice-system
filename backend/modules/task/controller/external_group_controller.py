"""外部群 Excel 导入、预览与人工关联接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.group_import_dto import CatalogBinding, CatalogQuery, GroupImportFile, ImportConfirm, PreviewQuery
from ..vo.group_import_vo import CatalogPage, ImportReceipt, ImportResult, PreviewPage
from ..vo.supplier_group_vo import GroupBinding


def create_router(previews, imports, catalog):
    router = APIRouter(prefix="/api/tasks/external-groups", tags=["外部群导入与关联"])

    @router.post("/import/preview", response_model=ImportReceipt)
    def preview(body: GroupImportFile, owner: Owner):
        return previews.create(body, owner)

    @router.post("/import/query", response_model=PreviewPage)
    def read_preview(body: PreviewQuery, owner: Owner):
        return previews.browse(body, owner)

    @router.post("/import/confirm", response_model=ImportResult)
    def confirm(body: ImportConfirm, owner: Owner):
        return imports.confirm(body, owner)

    @router.post("/query", response_model=CatalogPage)
    def browse(body: CatalogQuery, owner: Owner):
        return catalog.browse(body, owner)

    @router.post("/associate", response_model=GroupBinding)
    def associate(body: CatalogBinding, owner: Owner):
        return catalog.associate(body, owner)

    return router
