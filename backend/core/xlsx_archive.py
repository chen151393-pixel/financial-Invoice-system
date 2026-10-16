"""XLSX 归档大小与宏检查，供各业务导入器复用。"""

from io import BytesIO
from zipfile import ZipFile

from .errors import ApiError


def check_xlsx_archive(raw):
    with ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 32 * 1024 * 1024:
            raise ApiError(422, "XLSX解压后过大，请拆分文件")
        if any("vbaproject" in entry.filename.lower() for entry in entries):
            raise ApiError(422, "不支持包含宏的工作簿，请导出普通XLSX文件")
