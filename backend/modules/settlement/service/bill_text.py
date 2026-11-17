"""提单 PDF 文字提取：只取前几页文字；扫描件或损坏文件返回空字符串，由人工补填字段。"""

import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAX_PAGES = 5


def extract_text(content):
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES])
    except (PyPdfError, ValueError, KeyError, RecursionError):
        return ""
