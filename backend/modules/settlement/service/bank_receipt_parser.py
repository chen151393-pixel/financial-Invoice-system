"""银行导出的国际汇款明细。中文列名为准，保留原始行号。"""

import hashlib
import json
import re
from datetime import date, time
from decimal import Decimal

from backend.core.errors import ApiError
from backend.core.names import normalize_name
from backend.core.xlsx_reader import Cell, read_xlsx_sheets

REQUIRED = (
    "交易类型",
    "付款人名称",
    "境外收货人名称",
    "收款人账号",
    "收款人名称",
    "交易日期",
    "交易货币",
    "交易金额",
)
OPTIONAL = ("交易时间", "付款人账号", "付款人开户行号", "收款人开户行行号", "银行流水号")
AMOUNT = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,6})?")
EMPTY = Cell("")


def _header(rows):
    for index, row in enumerate(rows[:20]):
        names = [re.split(r"[\[【]", cell.text, maxsplit=1)[0].strip() for cell in row]
        if "交易日期" not in names or "交易金额" not in names:
            continue
        missing = [name for name in REQUIRED if name not in names]
        if missing:
            raise ApiError(422, f"银行流水缺少表头：{'、'.join(missing)}")
        recognized = [name for name in names if name in REQUIRED or name in OPTIONAL]
        if len(recognized) != len(set(recognized)):
            raise ApiError(422, "银行流水表头有重复列")
        return index, {name: names.index(name) for name in recognized}
    return None


def _value(cell, label, limit, *, required=True, identifier=False):
    if not cell.text:
        if required:
            raise ValueError(f"{label}不能为空")
        return None
    if len(cell.text) > limit:
        raise ValueError(f"{label}超过{limit}个字符")
    if identifier and cell.numeric and (not cell.text.isdigit() or len(cell.text) > 15):
        raise ValueError(f"{label}请按文本保存，避免号码精度丢失")
    return cell.text


def _date(value):
    if re.fullmatch(r"[0-9]{8}", value):
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    try:
        day = date.fromisoformat(value)
        if day.year >= 1000 and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return day
    except ValueError:
        pass
    raise ValueError("交易日期无效，请使用 YYYYMMDD 或 YYYY-MM-DD")


def _time(value):
    if not value:
        return None
    if re.fullmatch(r"[0-9]{2}:[0-9]{2}(?::[0-9]{2})?", value):
        try:
            return time.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("交易时间无效，请使用 HH:MM:SS")


def _amount(value):
    if AMOUNT.fullmatch(value):
        number = Decimal(value.replace(",", ""))
        if 0 < number < Decimal("1e18"):
            return number
    raise ValueError("交易金额须大于零，整数最多18位，小数最多6位")


def _row(cells, mapping, source_row, file_digest):
    def get(name):
        index = mapping.get(name, len(cells))
        return cells[index] if index < len(cells) else EMPTY

    if _value(get("交易类型"), "交易类型", 40) != "来账":
        return None
    day = _date(_value(get("交易日期"), "交易日期", 30))
    hour = _time(get("交易时间").text)
    company = _value(get("收款人名称"), "收款人名称", 200)
    account = _value(get("收款人账号"), "收款人账号", 200, identifier=True)
    payer = _value(get("付款人名称"), "付款人名称", 500)
    customer = _value(get("境外收货人名称"), "境外收货人名称", 500)
    currency = _value(get("交易货币"), "交易货币", 3).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("交易货币须为三字母币种代码")
    amount = _amount(_value(get("交易金额"), "交易金额", 40))
    reference = _value(get("银行流水号"), "银行流水号", 200, required=False, identifier=True)
    receiver = (normalize_name(account), day.isoformat(), currency)
    if reference:
        identity = ("reference", *receiver, reference)
    elif hour is not None:
        identity = (
            "transaction",
            *receiver,
            hour.isoformat(),
            format(amount.normalize(), "f"),
            normalize_name(company),
            normalize_name(payer),
            normalize_name(get("付款人账号").text),
            normalize_name(get("付款人开户行号").text),
            normalize_name(get("收款人开户行行号").text),
        )
    else:
        # 日期相同且缺交易时间/流水号时，只判定同一原始文件同一行的重试。
        identity = ("file", file_digest, source_row)
    import_key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return {
        "receipt_date": day,
        "receipt_time": hour,
        "receiving_company": company,
        "receiving_account": account,
        "payer_name": payer,
        "payer_key": normalize_name(payer),
        "customer_name": customer,
        "customer_key": normalize_name(customer),
        "currency": currency,
        "amount": amount,
        "reference": reference,
        "source_row": source_row,
        "import_key": import_key,
    }


def parse_bank_receipts(raw):
    digest = hashlib.sha256(raw).hexdigest()
    found = False
    entries = []
    ignored = 0
    for sheet, rows in read_xlsx_sheets(raw, max_rows=6020, max_columns=80, allow_trailing_blank_rows=True):
        header = _header(rows)
        if header is None:
            continue
        if found:
            raise ApiError(422, "工作簿有多张银行流水表，请按工作表分别导入")
        found = True
        header_index, mapping = header
        for row_no, cells in enumerate(rows[header_index + 1 :], header_index + 2):
            if not any(cell.text for cell in cells):
                continue
            try:
                entry = _row(cells, mapping, row_no, digest)
            except ValueError as exc:
                raise ApiError(422, f"{sheet} 第 {row_no} 行：{exc}") from None
            if entry is None:
                ignored += 1
            else:
                entries.append(entry)
    if not found:
        raise ApiError(
            422, "找不到银行流水表头，请使用含「交易日期」「交易金额」「境外收货人名称」的银行导出表"
        )
    if not entries:
        raise ApiError(422, "表格中没有可导入的来账记录")
    return entries, ignored
