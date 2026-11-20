"""结汇 PDF 原件可读性校验；与文字识别分开，损坏文件不能通过人工补填变成有效资料。"""

import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from backend.core.errors import ApiError


def validate_pdf(content, label):
    if not content.startswith(b"%PDF-"):
        raise ApiError(422, f"{label}须为 PDF 文件")
    try:
        pdf = PdfReader(io.BytesIO(content))
        if pdf.is_encrypted or not pdf.pages:
            raise ApiError(422, f"{label}不能加密，且至少需要一页")
        # 访问所有页面的内容流，识别截断文件；扫描件没有文字层也属于有效原件。
        for page in pdf.pages:
            contents = page.get_contents()
            if contents is not None:
                contents.get_data()
    except (PyPdfError, ValueError, KeyError, IndexError, TypeError, OSError, RecursionError):
        raise ApiError(422, f"{label} PDF 无法读取，请重新选择原件") from None
