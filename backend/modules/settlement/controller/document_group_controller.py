"""直接收汇资料组入口；复用既有提单、合同、打包用例。"""

from uuid import UUID

from fastapi import APIRouter, Path

from backend.core.dependencies import Owner

from ..dto.document_group_dto import ConfirmGroupBasis, CreateDocumentGroup, DocumentGroupQuery
from ..service.document_group_basis_service import DocumentGroupBasisService
from ..vo.document_group_vo import DocumentGroup, DocumentGroupList, DocumentMergeResult, GroupBasisPreview


def create_router(service, merges=None):
    router = APIRouter(prefix="/api/settlement/direct-document-groups", tags=["直接收汇资料组"])

    @router.post("/query", response_model=DocumentGroupList)
    def query(body: DocumentGroupQuery, owner: Owner):
        return service.query(body)

    @router.post("", response_model=DocumentGroup)
    def create(body: CreateDocumentGroup, owner: Owner):
        return service.create(body, owner)

    from ..dto.document_merge_dto import SingleDocumentGroupRequest

    @router.post("/single", response_model=DocumentGroup)
    def single(body: SingleDocumentGroupRequest, owner: Owner):
        return service.ensure_single(body.declarationNo, owner)

    basis = DocumentGroupBasisService(service)

    @router.get("/{group_id}/source-preview", response_model=GroupBasisPreview)
    def source_preview(owner: Owner, group_id: int = Path(ge=1)):
        return basis.preview(group_id)

    @router.post("/{group_id}/source", response_model=DocumentGroup)
    def source_confirm(body: ConfirmGroupBasis, owner: Owner, group_id: int = Path(ge=1)):
        return basis.confirm(group_id, body, owner)

    if merges is not None:
        from ..dto.document_merge_dto import (
            DocumentMergePreviewRequest,
            DocumentMergeQuery,
            MergeDocumentGroupsRequest,
        )
        from ..vo.document_merge_vo import DocumentMergeCandidates, DocumentMergePreview

        @router.get("/merge/requests/{request_id}", response_model=DocumentMergeResult)
        def merge_result(request_id: UUID, owner: Owner):
            return DocumentMergeResult(group=merges.result(str(request_id)))

        @router.post("/merge/query", response_model=DocumentMergeCandidates)
        def candidates(body: DocumentMergeQuery, owner: Owner):
            return merges.query(body)

        @router.post("/merge/preview", response_model=DocumentMergePreview)
        def preview(body: DocumentMergePreviewRequest, owner: Owner):
            return merges.preview(body)

        @router.post("/merge", response_model=DocumentGroup)
        def merge(body: MergeDocumentGroupsRequest, owner: Owner):
            return merges.merge(body, owner)

    @router.get("/{group_id}", response_model=DocumentGroup)
    def detail(owner: Owner, group_id: int = Path(ge=1)):
        return service.get(group_id)

    return router
