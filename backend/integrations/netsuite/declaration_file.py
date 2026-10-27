"""报关原件格式：兼容旧 PDF 响应，显式接受原打印脚本的 SpreadsheetML。"""

import base64
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from .restlet_file import PDF_LIMIT, decode_pdf

SPREADSHEET = "urn:schemas-microsoft-com:office:spreadsheet"
EXCEL_TYPES = {"customs_declaration", "invoice"}


def decode_file(item, doc_type):
    """返回经过校验的正文、格式和固定扩展名；不信任远端文件名。"""
    if not isinstance(item, dict):
        raise ValueError("invalid file")
    format_name = item.get("format", "pdf")
    encoded = item.get("contentBase64")
    if format_name == "pdf":
        return {"content": decode_pdf(encoded), "format": "pdf", "extension": ".pdf"}
    if format_name != "excel_xml" or doc_type not in EXCEL_TYPES or not isinstance(encoded, str):
        raise ValueError("unsupported format")
    # 在解码前限制长度，单文件沿用 PDF 的 7 MB 上限。
    if len(encoded) > ((PDF_LIMIT + 2) // 3) * 4:
        raise ValueError("file too large")
    content = base64.b64decode(encoded, validate=True)
    if not content or len(content) > PDF_LIMIT:
        raise ValueError("invalid file size")
    try:
        # 原 NS 发票模板在 XML 声明前带空格；只为解析去除，归档仍保留原件字节。
        xml = content.decode("utf-8-sig").lstrip()
        if "<?xml-stylesheet" in xml.lower():
            raise ValueError("external stylesheet")
        root = fromstring(xml, forbid_dtd=True)
    except (ParseError, DefusedXmlException) as error:
        raise ValueError("invalid spreadsheet XML") from error
    if root.tag != f"{{{SPREADSHEET}}}Workbook":
        raise ValueError("not a spreadsheet workbook")
    sheets = root.findall(f"{{{SPREADSHEET}}}Worksheet")
    if not sheets or any(sheet.find(f"{{{SPREADSHEET}}}Table") is None for sheet in sheets):
        raise ValueError("missing worksheet table")
    # 此通道只接收打印值与样式，拒绝可执行公式、链接及外部数据连接。
    forbidden_tags = {
        "script",
        "macro",
        "excel4macros",
        "externalworkbook",
        "querytable",
        "connection",
        "dde",
    }
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() in forbidden_tags:
            raise ValueError("active spreadsheet content")
        if any(key.rsplit("}", 1)[-1].lower() in {"formula", "href"} for key in element.attrib):
            raise ValueError("formula or external link")
    return {"content": content, "format": "excel_xml", "extension": ".xls"}
