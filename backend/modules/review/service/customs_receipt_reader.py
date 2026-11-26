"""读取海关回执文件为原始文本行；不判断列含义，列识别与校验由 customs_receipt_parser 负责。

支持单一窗口导出的 .xlsx / .xls 与另存的 .csv。长号码（出口报关单号）若被 Excel 存为数字会丢失精度，
读取时保留单元格类型供解析器拒绝。
"""

import csv
import io

import xlrd
from xlrd.compdoc import CompDocError

from backend.core.errors import ApiError
from backend.core.xlsx_reader import Cell, number_text, read_xlsx_sheets

MAX_ROWS = 100000
MAX_COLUMNS = 80
MAX_CELL = 1000


def _check_size(sheet_name, row_count, column_count):
    if row_count > MAX_ROWS + 20 or column_count > MAX_COLUMNS:
        raise ApiError(422, f"{sheet_name}超过{MAX_ROWS}行或{MAX_COLUMNS}列，请拆分文件")


def _xls_sheets(raw):
    if not raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise ApiError(422, "文件不是有效的XLS工作簿，请勿仅修改扩展名")
    try:
        book = xlrd.open_workbook(file_contents=raw, on_demand=True)
    except (xlrd.XLRDError, CompDocError, ValueError, AssertionError):
        raise ApiError(422, "文件不是有效的XLS工作簿") from None
    try:
        for sheet in book.sheets():
            _check_size(sheet.name, sheet.nrows, sheet.ncols)
            rows = []
            for index in range(sheet.nrows):
                row = []
                for col in range(sheet.ncols):
                    cell = sheet.cell(index, col)
                    if cell.ctype == xlrd.XL_CELL_ERROR:
                        raise ApiError(422, f"{sheet.name}第{index + 1}行有Excel错误值")
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        value = xlrd.xldate_as_datetime(cell.value, book.datemode).date().isoformat()
                        row.append(Cell(value))
                    elif cell.ctype == xlrd.XL_CELL_NUMBER:
                        row.append(Cell(number_text(cell.value), numeric=True))
                    else:
                        row.append(Cell(str(cell.value).strip()))
                rows.append(row)
            yield sheet.name, rows
    finally:
        book.release_resources()


def _csv_sheets(raw):
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ApiError(422, "CSV 文件编码无法识别，请另存为 UTF-8 或使用 Excel 文件")
    rows = []
    for row_no, values in enumerate(csv.reader(io.StringIO(text)), 1):
        _check_size("CSV", row_no, len(values))
        rows.append([Cell(value.strip()) for value in values])
    yield "CSV", rows


def read_sheets(filename, raw):
    """逐个工作表产出 (名称, [[Cell, ...], ...])；单元格过长时拒绝。"""
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        sheets = read_xlsx_sheets(
            raw,
            max_rows=MAX_ROWS + 20,
            max_columns=MAX_COLUMNS,
            allow_trailing_blank_rows=True,
            max_uncompressed_bytes=256 * 1024 * 1024,
        )
    elif lower.endswith(".xls"):
        sheets = _xls_sheets(raw)
    elif lower.endswith(".csv"):
        sheets = _csv_sheets(raw)
    else:
        raise ApiError(422, "请选择 .xlsx、.xls 或 .csv 格式的海关回执")
    for name, rows in sheets:
        for row_no, row in enumerate(rows, 1):
            if any(len(cell.text) > MAX_CELL for cell in row):
                raise ApiError(422, f"{name}第{row_no}行有单元格内容过长")
        yield name, rows
