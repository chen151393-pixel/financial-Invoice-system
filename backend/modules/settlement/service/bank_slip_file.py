"""人工登记的银行水单原件校验：只检查 PDF，不进行文字提取或 OCR。"""

from backend.core.errors import ApiError

from ..dto.bill_dto import MAX_BILL_BYTES
from .bill_service import decode
from .pdf_file import validate_pdf


def content_of(body):
    content = decode(body.content, MAX_BILL_BYTES, "银行水单")
    if not body.fileName.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
        raise ApiError(422, "银行水单须为 PDF 文件")
    validate_pdf(content, "银行水单")
    return content
