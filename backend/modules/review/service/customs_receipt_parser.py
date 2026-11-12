"""海关回执列识别与校验：把原始行整理为按出口报关单号分组的回执。

表头按别名识别（单一窗口不同导出版本列名略有差异），未识别的列忽略并告知页面。
同一报关单内项号不能重复；出口日期、境外收货人在同一报关单内必须一致。
"""

import base64
import binascii
import hashlib
import json
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from backend.core.errors import ApiError

from .customs_receipt_reader import MAX_ROWS, read_sheets

MAX_BYTES = 4 * 1024 * 1024
HEADER_SCAN_ROWS = 10

# 字段 → (页面名称, 可识别的表头)；表头比较前去除空白并做全半角统一
COLUMNS = {
    "declaration_no": ("出口报关单号", ("出口报关单号", "报关单号", "海关编号")),
    "item_no": ("项号", ("项号", "商品序号")),
    "export_date": ("出口日期", ("出口日期",)),
    "check_status": ("数据检查状态", ("数据检查状态",)),
    "tax_type": ("征免类型", ("征免类型", "征免方式", "征免")),
    "hs_code": ("商品代码", ("商品代码", "商品编号", "商品编码")),
    "name": ("海关商品名称", ("海关商品名称", "商品名称")),
    "specification": ("规格型号", ("规格型号",)),
    "contract_no": ("出口合同号", ("出口合同号", "合同协议号", "合同号")),
    "deal_unit": ("成交单位", ("成交单位", "成交计量单位")),
    "deal_quantity": ("成交数量", ("成交数量",)),
    "currency": ("成交货币", ("成交货币", "成交币制", "币制")),
    "deal_total": ("成交总价", ("成交总价", "总价")),
    "usd_fob": ("美元离岸价", ("美元离岸价",)),
    "legal_unit": ("法定单位", ("法定单位", "法定计量单位", "法定第一计量单位")),
    "legal_quantity": ("法定数量", ("法定数量", "法定出口数量", "法定第一数量", "法定单位出口数量")),
    "customs_doc": ("关单信息", ("关单信息",)),
    "usage_flag": ("使用标志", ("使用标志",)),
    "consignee": ("境外收货人", ("境外收货人",)),
}
REQUIRED = ("declaration_no", "item_no", "name", "deal_unit", "deal_quantity")
# 长度上限与实体列一致
TEXT_LIMITS = {
    "check_status": 40,
    "tax_type": 40,
    "hs_code": 20,
    "name": 500,
    "specification": 500,
    "contract_no": 100,
    "deal_unit": 50,
    "currency": 20,
    "legal_unit": 50,
    "customs_doc": 20,
    "usage_flag": 20,
    "consignee": 500,
}
NUMBERS = {"deal_quantity": 8, "legal_quantity": 8, "deal_total": 6, "usd_fob": 6}
DECLARATION_NO = re.compile(r"^[0-9A-Za-z-]{6,60}$")
# 海关导出用“--”表示无值
EMPTY_MARKS = {"", "--", "—", "-"}


def _header_key(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


ALIASES = {_header_key(alias): key for key, (_, aliases) in COLUMNS.items() for alias in aliases}


def _locate_header(rows):
    """前若干行中第一行包含全部必需列的作为表头；返回 (行下标, {列号: 字段}, 忽略列)。"""
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        mapping, ignored = {}, []
        for col, cell in enumerate(row):
            key = ALIASES.get(_header_key(cell.text))
            if key and key not in mapping.values():
                mapping[col] = key
            elif cell.text:
                ignored.append(cell.text)
        if set(REQUIRED) <= set(mapping.values()):
            return index, mapping, ignored
    return None


def _number(text, scale, label):
    cleaned = text.replace(",", "").replace("，", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ApiError(422, f"{label}不是有效数值") from None
    if not value.is_finite() or abs(value) >= Decimal(10) ** 17 or value < 0:
        raise ApiError(422, f"{label}超出允许范围")
    if value != value.quantize(Decimal(10) ** -scale):
        raise ApiError(422, f"{label}超过{scale}位小数")
    return value


def _date(text, label):
    try:
        return date.fromisoformat(text.replace("/", "-").replace(".", "-")[:10])
    except ValueError:
        raise ApiError(422, f"{label}须为日期，如 2026-10-30") from None


def _item_no(text, label):
    if not re.fullmatch(r"[0-9]{1,4}", text):
        raise ApiError(422, f"{label}须为数字")
    return f"{int(text):02d}"


def _row(sheet, row_no, cells, mapping):
    values = {}
    for col, key in mapping.items():
        cell = cells[col] if col < len(cells) else None
        text = cell.text if cell else ""
        label = f"{sheet}第{row_no}行{COLUMNS[key][0]}"
        if key == "declaration_no" and cell is not None and cell.numeric:
            raise ApiError(422, f"{label}须为文本格式，数字格式会丢失长号码精度")
        if text in EMPTY_MARKS:
            values[key] = None
            continue
        if key == "declaration_no":
            if not DECLARATION_NO.fullmatch(text):
                raise ApiError(422, f"{label}格式不正确")
            values[key] = text
        elif key == "item_no":
            values[key] = _item_no(text, label)
        elif key == "export_date":
            values[key] = _date(text, label)
        elif key in NUMBERS:
            values[key] = _number(text, NUMBERS[key], label)
        else:
            if len(text) > TEXT_LIMITS[key]:
                raise ApiError(422, f"{label}超过{TEXT_LIMITS[key]}个字符")
            values[key] = text
    for key in REQUIRED:
        if values.get(key) is None:
            raise ApiError(422, f"{sheet}第{row_no}行缺少{COLUMNS[key][0]}")
    return values


def _same(declaration, field, value, label):
    """同一报关单内各项的出口日期、境外收货人须一致；空值不参与比较。"""
    if value is None:
        return
    current = declaration.get(field)
    if current is None:
        declaration[field] = value
    elif current != value:
        raise ApiError(
            422, f"出口报关单号 {declaration['declaration_no']} 的{label}前后不一致：{current} / {value}"
        )


def content_digest(declaration):
    """回执内容摘要：出口日期、境外收货人与按项号排序的全部明细字段。"""
    payload = {
        "export_date": declaration["export_date"],
        "consignee": declaration["consignee"],
        "lines": sorted(
            ({k: v for k, v in line.items() if k != "source_row"} for line in declaration["lines"]),
            key=lambda line: line["item_no"],
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def decode(filename, content):
    if not filename or any(c in filename for c in ("/", "\\", "\x00")):
        raise ApiError(422, "文件名不能包含路径")
    try:
        raw = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error):
        raise ApiError(422, "文件编码损坏，请重新选择原文件") from None
    if not raw or len(raw) > MAX_BYTES:
        raise ApiError(413, "文件大小须在4MB以内")
    return raw


def parse(filename, content):
    """返回 {declarations: [...], rows, columns, ignored}；任何一行有误时整份文件不导入。"""
    raw = decode(filename, content)
    for sheet, rows in read_sheets(filename, raw):
        located = _locate_header(rows)
        if located is None:
            continue
        header_index, mapping, ignored = located
        declarations, count = {}, 0
        for offset, cells in enumerate(rows[header_index + 1 :], header_index + 2):
            if not any(cell.text for cell in cells):
                continue
            count += 1
            if count > MAX_ROWS:
                raise ApiError(422, f"{sheet}超过{MAX_ROWS}行明细，请拆分文件")
            values = _row(sheet, offset, cells, mapping)
            number = values.pop("declaration_no")
            declaration = declarations.setdefault(
                number,
                {"declaration_no": number, "export_date": None, "consignee": None, "lines": [], "items": {}},
            )
            _same(declaration, "export_date", values.pop("export_date", None), "出口日期")
            _same(declaration, "consignee", values.pop("consignee", None), "境外收货人")
            item = values["item_no"]
            if item in declaration["items"]:
                raise ApiError(
                    422,
                    f"出口报关单号 {number} 项号 {item} 重复（第{declaration['items'][item]}行与第{offset}行）",
                )
            declaration["items"][item] = offset
            line = {
                key: values.get(key)
                for key in COLUMNS
                if key not in {"declaration_no", "export_date", "consignee"}
            }
            declaration["lines"].append({**line, "source_row": offset})
        if not declarations:
            raise ApiError(422, f"{sheet}没有海关回执明细")
        result = []
        for declaration in declarations.values():
            declaration.pop("items")
            result.append({**declaration, "content_sha256": content_digest(declaration)})
        return {
            "declarations": result,
            "rows": count,
            "columns": [COLUMNS[key][0] for key in COLUMNS if key in mapping.values()],
            "ignored": ignored,
        }
    names = "、".join(COLUMNS[key][0] for key in REQUIRED)
    raise ApiError(422, f"没有找到海关回执表头，须包含：{names}")
