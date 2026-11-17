"""结汇资料接口：提单上传 / 修改 / 移除、按模板生成销售合同、资料包下载。齐全度与可操作判断在后端。"""

from urllib.parse import quote

from fastapi import APIRouter, Path, Response

from backend.core.dependencies import Owner

from ..dto.bill_dto import UpdateBillRequest, UploadBillRequest
from ..dto.contract_dto import GenerateContractsRequest
from ..vo.document_vo import BatchDocuments

BatchId = Path(ge=1)
# FastAPI 会把参数名写入 Path 对象，不同名称的路径参数不能共用同一个对象
BillId = Path(ge=1)
ContractId = Path(ge=1)
# 提单以 base64 放在 JSON 中：8 MB 文件编码后约 10.7 MB
JSON_BODY_LIMITS = {r"/api/settlement/batches/\d+/bills": 12 * 1024 * 1024}


def download(filename, content, media_type, *, inline):
    disposition = "inline" if inline else "attachment"
    headers = {
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=content, media_type=media_type, headers=headers)


def create_router(documents, bills, contracts, packages):
    router = APIRouter(prefix="/api/settlement/batches/{batch_id}", tags=["结汇资料"])

    @router.get("/documents", response_model=BatchDocuments)
    def get_documents(owner: Owner, batch_id: int = BatchId):
        return documents.get(batch_id)

    @router.post("/bills", response_model=BatchDocuments)
    def upload_bill(body: UploadBillRequest, owner: Owner, batch_id: int = BatchId):
        return bills.upload(batch_id, body, owner)

    @router.post("/bills/{bill_id}", response_model=BatchDocuments)
    def update_bill(body: UpdateBillRequest, owner: Owner, batch_id: int = BatchId, bill_id: int = BillId):
        return bills.update(batch_id, bill_id, body, owner)

    @router.post("/bills/{bill_id}/remove", response_model=BatchDocuments)
    def remove_bill(owner: Owner, batch_id: int = BatchId, bill_id: int = BillId):
        return bills.remove(batch_id, bill_id, owner)

    @router.get("/bills/{bill_id}/file")
    def bill_file(owner: Owner, batch_id: int = BatchId, bill_id: int = BillId):
        filename, content = bills.file(batch_id, bill_id)
        return download(filename, content, "application/pdf", inline=True)

    @router.post("/contracts/generate", response_model=BatchDocuments)
    def generate_contracts(body: GenerateContractsRequest, owner: Owner, batch_id: int = BatchId):
        return contracts.generate(batch_id, body, owner)

    @router.get("/contracts/{contract_id}/file")
    def contract_file(owner: Owner, batch_id: int = BatchId, contract_id: int = ContractId):
        filename, content = contracts.file(batch_id, contract_id)
        return download(filename, content, "application/pdf", inline=True)

    @router.get("/package")
    def package(owner: Owner, batch_id: int = BatchId):
        filename, content = packages.build(batch_id)
        return download(filename, content, "application/zip", inline=False)

    return router
