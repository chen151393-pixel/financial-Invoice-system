"""限量读取普通 XLSX 单元格，保留数字类型供业务检查原始精度。"""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .errors import ApiError
from .xlsx_archive import check_xlsx_archive


class Cell:
    __slots__ = ("text", "numeric")

    def __init__(self, text, numeric=False):
        self.text = text
        self.numeric = numeric


def number_text(value):
    return format(Decimal(str(value)).normalize(), "f")


def _cell(sheet, row_no, cell):
    value = cell.value
    if cell.data_type == "f":
        raise ApiError(422, f"{sheet}第{row_no}行包含公式，请粘贴为值后重新导入")
    if cell.data_type == "e":
        raise ApiError(422, f"{sheet}第{row_no}行有Excel错误值")
    if isinstance(value, datetime):
        return Cell(value.date().isoformat())
    if isinstance(value, date):
        return Cell(value.isoformat())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Cell(number_text(value), numeric=True)
    return Cell("" if value is None else str(value).strip())


def read_xlsx_sheets(
    raw,
    *,
    max_rows,
    max_columns,
    allow_trailing_blank_rows=False,
    max_uncompressed_bytes=32 * 1024 * 1024,
):
    """返回工作表名和文本行。按实际行读取，不依赖 Excel 声明的工作表尺寸。"""
    try:
        check_xlsx_archive(raw, max_uncompressed_bytes=max_uncompressed_bytes)
        book = load_workbook(BytesIO(raw), read_only=True, data_only=False, keep_links=False)
        try:
            for sheet in book.worksheets:
                sheet.reset_dimensions()
                rows = []
                for row_no, cells in enumerate(sheet.iter_rows(), 1):
                    if allow_trailing_blank_rows:
                        # 样式单元格不算数据；公式/错误即使显示为空也必须继续校验。
                        end = len(cells)
                        while (
                            end
                            and cells[end - 1].data_type not in {"f", "e"}
                            and (
                                cells[end - 1].value is None
                                or isinstance(cells[end - 1].value, str)
                                and not cells[end - 1].value.strip()
                            )
                        ):
                            end -= 1
                        cells = cells[:end]
                    if (
                        allow_trailing_blank_rows
                        and max_rows < row_no <= 1_048_576
                        and not any(cell.value is not None for cell in cells)
                    ):
                        continue
                    if row_no > max_rows or len(cells) > max_columns:
                        raise ApiError(422, f"{sheet.title}超过{max_rows}行或{max_columns}列，请拆分文件")
                    rows.append([_cell(sheet.title, row_no, cell) for cell in cells])
                yield sheet.title, rows
        finally:
            book.close()
    except (BadZipFile, InvalidFileException, KeyError, OSError, ParseError, DefusedXmlException):
        raise ApiError(422, "文件不是有效的XLSX工作簿，请勿仅修改扩展名") from None
