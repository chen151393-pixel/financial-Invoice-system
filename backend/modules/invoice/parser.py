"""柠檬云进项XLS解析与源数据校验，不执行宏、不采信文件内指令。"""

import base64
import binascii
import hashlib
import json
import re
import struct
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

import xlrd
from xlrd.compdoc import CompDocError

from backend.core.errors import ApiError

from .xlsx_reader import read_xlsx

HEADERS = "发票种类 录入日期 开票日期 发票代码 发票号码 发票状态 认证日期 税款所属期 供应商名称 项目 部门 职员 纳税人识别号 地址及电话 开户行及账号 业务类型 合计金额 税率 合计税额 价税合计 记账期间 关联凭证 备注".split()
LINE_HEADERS = "发票种类 开票日期 发票代码 发票号码 商品名称 规格型号 单位 数量 金额 税率 税额 进项类型 计税方法 印花税税目 印花税子目".split()
HEAD_MAP = dict(
    zip(
        HEADERS,
        "invoice_type_name entry_date invoice_date invoice_code invoice_no invoice_status_raw certification_date tax_period seller_name project_name department_name employee_name seller_tax_no seller_address_phone seller_bank_account business_type_name amount_excluding_tax tax_rate_summary tax_amount amount_including_tax accounting_period voucher_reference remark".split(),
        strict=True,
    )
)
LINE_MAP = dict(
    zip(
        LINE_HEADERS[4:],
        "item_name specification unit_name quantity amount_excluding_tax tax_rate_raw tax_amount input_type_name taxation_method_name stamp_tax_category stamp_tax_subcategory".split(),
        strict=True,
    )
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def number(value, scale, label, optional=False):
    if value is None and optional:
        return None
    try:
        result = Decimal(value or "")
        if not result.is_finite() or abs(result) >= Decimal(10) ** 18:
            raise ValueError()
        if result != result.quantize(Decimal(10) ** -scale):
            raise ValueError()
        return result
    except (InvalidOperation, ValueError):
        raise ApiError(422, f"{label}不是有效数值或超过允许精度") from None


def day(value, label, optional=False):
    if value is None and optional:
        return None
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        raise ApiError(422, f"{label}须为YYYY-MM-DD日期") from None


def rows(sheet, headers, datemode, keys=None):
    if sheet.nrows > 6001 or sheet.ncols != len(headers):
        raise ApiError(422, f"{sheet.name}列数不符或超过6000行，请拆分文件")
    if sheet.nrows == 0 or sheet.row_values(0) != headers:
        raise ApiError(422, f"{sheet.name}表头与柠檬云导出模板不一致")
    result = []
    for index in range(1, sheet.nrows):
        values = {}
        for col, name in enumerate(headers):
            cell = sheet.cell(index, col)
            if cell.ctype == xlrd.XL_CELL_ERROR:
                raise ApiError(422, f"{sheet.name}第{index + 1}行{name}为Excel错误值")
            if name in {"发票代码", "发票号码", "纳税人识别号"} and cell.ctype == xlrd.XL_CELL_NUMBER:
                raise ApiError(422, f"{sheet.name}第{index + 1}行{name}须为文本，避免长号码精度丢失")
            if cell.ctype == xlrd.XL_CELL_DATE:
                value = xlrd.xldate_as_datetime(cell.value, datemode).date().isoformat()
            elif cell.ctype == xlrd.XL_CELL_NUMBER:
                value = format(Decimal(str(cell.value)).normalize(), "f")
            else:
                value = str(cell.value).strip()
            if len(value) > 4000:
                raise ApiError(422, f"{sheet.name}第{index + 1}行{name}过长")
            values[(keys or headers)[col]] = value or None
        if any(v is not None for v in values.values()):
            result.append((index + 1, values))
    return result


def parse_file(filename, content):
    if not filename.lower().endswith((".xls", ".xlsx")) or any(c in filename for c in ("/", "\\", "\x00")):
        raise ApiError(422, "请选择柠檬云导出的.xls或.xlsx文件，文件名不能包含路径")
    try:
        raw = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error):
        raise ApiError(422, "文件编码损坏，请重新选择原文件") from None
    if not raw or len(raw) > 4 * 1024 * 1024:
        raise ApiError(413, "文件大小须在4MB以内")
    if filename.lower().endswith(".xlsx"):
        heads, lines, combined_sheet = read_xlsx(raw, HEADERS, LINE_HEADERS)
        documents = build_combined(heads, combined_sheet) if combined_sheet else build_documents(heads, lines)
        return documents, hashlib.sha256(raw).hexdigest()
    if not raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise ApiError(422, "文件不是有效的XLS工作簿，请勿仅修改扩展名")
    try:
        book = xlrd.open_workbook(file_contents=raw, on_demand=True)
        try:
            combined = HEADERS + LINE_HEADERS[4:]
            candidates = [sheet for sheet in book.sheets() if sheet.nrows and sheet.row_values(0) == combined]
            if len(candidates) > 1 or (candidates and {"发票信息", "货物信息"} <= set(book.sheet_names())):
                raise ApiError(422, "存在多个导入模板，请每次只保留一张合并表或一套双表模板")
            if candidates:
                sheet = candidates[0]
                combined_rows = rows(
                    sheet, combined, book.datemode, HEADERS + ["明细_" + name for name in LINE_HEADERS[4:]]
                )
                return build_combined(combined_rows, sheet.name), hashlib.sha256(raw).hexdigest()
            if not {"发票信息", "货物信息"} <= set(book.sheet_names()):
                raise ApiError(
                    422, "未识别工作表：请使用34列票头与商品合并表，或“发票信息”“货物信息”双表模板"
                )
            heads = rows(book.sheet_by_name("发票信息"), HEADERS, book.datemode)
            lines = rows(book.sheet_by_name("货物信息"), LINE_HEADERS, book.datemode)
        finally:
            book.release_resources()
    except (xlrd.XLRDError, CompDocError, struct.error, IndexError, UnicodeError, ValueError) as error:
        raise ApiError(422, "无法读取XLS文件，请重新从柠檬云导出") from error
    return build_documents(heads, lines), hashlib.sha256(raw).hexdigest()


def build_combined(source, sheet_name):
    """合并表按票号归组；小计只核验，不伪装成商品或重复票头。"""
    heads, lines, subtotals = {}, [], {}
    for row, raw in source:
        head = {name: raw[name] for name in HEADERS}
        no = head["发票号码"]
        if no in heads and heads[no][1] != head:
            raise ApiError(422, f"{sheet_name}第{row}行同票号的票头字段不一致")
        heads.setdefault(no, (row, head))
        line = {name: raw[name] for name in LINE_HEADERS[:4]}
        line.update({name: raw["明细_" + name] for name in LINE_HEADERS[4:]})
        if line["商品名称"] == "合计":
            if no in subtotals:
                raise ApiError(422, f"{sheet_name}第{row}行同一发票存在重复合计行")
            subtotals[no] = (row, line)
        else:
            lines.append((row, line))
    documents = build_documents(list(heads.values()), lines)
    for doc in documents:
        no = doc["head"]["invoice_no"]
        doc["rawHead"]["sheet"] = sheet_name
        for raw in doc["rawLines"]:
            raw["sheet"] = sheet_name
        if no not in subtotals:
            continue
        row, subtotal = subtotals[no]
        label = f"{sheet_name}第{row}行合计"
        for name, field in [("金额", "amount_excluding_tax"), ("税额", "tax_amount")]:
            if number(subtotal[name], 6, label) != doc["head"][field]:
                raise ApiError(422, f"{label}与发票金额不一致")
        quantities = [line["quantity"] for line in doc["lines"]]
        if subtotal["数量"] is not None and (
            any(q is None for q in quantities) or number(subtotal["数量"], 8, label) != sum(quantities)
        ):
            raise ApiError(422, f"{label}数量与商品明细不一致")
        doc["rawHead"]["subtotal"] = {"sheet": sheet_name, "row": row, "values": subtotal}
    return documents


def build_documents(heads, lines):
    documents = {}
    total_rows = []
    for row, raw in heads:
        if raw["业务类型"] == "合计" and not raw["发票号码"]:
            total_rows.append(raw)
            continue
        label = f"发票信息第{row}行"
        no = raw["发票号码"] or ""
        if not re.fullmatch(r"[0-9]{20}", no) or not (raw["发票种类"] or "").startswith("数电发票"):
            raise ApiError(422, f"{label}当前仅支持具有20位文本票号的数电进项发票")
        if no in documents:
            raise ApiError(422, f"{label}发票号码重复")
        head = {target: raw[source] for source, target in HEAD_MAP.items()}
        for field in ("invoice_date", "entry_date", "certification_date"):
            head[field] = day(head[field], label, optional=field != "invoice_date")
        for field in ("tax_period", "accounting_period"):
            if head[field] and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", head[field]):
                raise ApiError(422, f"{label}税款或记账期间须为YYYY-MM")
        for field in ("amount_excluding_tax", "tax_amount", "amount_including_tax"):
            head[field] = number(head[field], 6, label)
        if not head["seller_name"] or not head["seller_tax_no"]:
            raise ApiError(422, f"{label}缺少供应商名称或税号")
        head.update(
            invoice_direction="input",
            invoice_status={"正常": "normal", "已红冲": "red_offset", "作废": "void"}.get(
                raw["发票状态"], "unknown"
            ),
        )
        documents[no] = {"head": head, "lines": [], "rawHead": {"row": row, "values": raw}, "rawLines": []}
    if not documents or len(documents) > 1000:
        raise ApiError(422, "每次须导入1至1000张发票")
    for row, raw in lines:
        document = documents.get(raw["发票号码"])
        label = f"货物信息第{row}行"
        if not document:
            raise ApiError(422, f"{label}找不到对应发票")
        original = document["rawHead"]["values"]
        if any(raw[key] != original[key] for key in LINE_HEADERS[:4]):
            raise ApiError(422, f"{label}票种、日期或代码与票头不一致")
        line = {target: raw[source] for source, target in LINE_MAP.items()}
        if not line["item_name"]:
            raise ApiError(422, f"{label}缺少商品名称")
        for field in ("amount_excluding_tax", "tax_amount", "quantity"):
            line[field] = number(
                line[field], 8 if field == "quantity" else 6, label, optional=field == "quantity"
            )
        rate = raw["税率"] or ""
        line["tax_rate"] = None
        line["tax_treatment"] = {"免税": "exempt", "不征税": "non_taxable"}.get(rate, "unknown")
        if re.fullmatch(r"\d+(\.\d+)?%", rate):
            tax = number(rate[:-1], 6, label) / 100
            if not 0 <= tax <= 1:
                raise ApiError(422, f"{label}税率超出范围")
            line.update(tax_rate=tax, tax_treatment="rate")
        line["amount_including_tax"] = line["amount_excluding_tax"] + line["tax_amount"]
        document["lines"].append(line)
        document["rawLines"].append({"row": row, "values": raw})
    for no, doc in documents.items():
        head = doc["head"]
        if not doc["lines"] or any(
            sum(line[field] for line in doc["lines"]) != head[field]
            for field in ("amount_excluding_tax", "tax_amount", "amount_including_tax")
        ):
            raise ApiError(422, f"发票{no}缺少明细或明细汇总与票头金额不一致")
        counts = Counter()
        hashes = []
        for index, line in enumerate(doc["lines"], 1):
            key = digest(line)
            hashes.append(key)
            counts[key] += 1
            line.update(source_line_key=f"{key}:{counts[key]}", line_no=str(index))
        head["content_hash"] = digest({"head": head, "lines": sorted(hashes)})
        head["import_key"] = digest({"version": 1, "type": "digital", "no": no})
    for raw in total_rows:
        for name, field in (
            ("合计金额", "amount_excluding_tax"),
            ("合计税额", "tax_amount"),
            ("价税合计", "amount_including_tax"),
        ):
            if number(raw[name], 6, "合计行") != sum(doc["head"][field] for doc in documents.values()):
                raise ApiError(422, "文件末尾合计与发票汇总不一致")
    return list(documents.values())
