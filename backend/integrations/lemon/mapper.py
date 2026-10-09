"""open2 原始发票 -> 内部发票两表字段（占位映射，字段名待 open2 实测复核）。

设计文档 docs/lemon-invoice-sync-plan.md 口径 B：账套已录入进项票。这里只做对象转换，
不访问数据库、不解析业务金额规则。映射目标列名来自 modules/invoice/parser.py 的
HEAD_MAP / LINE_MAP 与 storage_values（invoices / invoice_lines 两表）。

待 open2 实测复核（见设计文档 §6 #2）：
- 日期范围参数名、GetInvoice 是否直接带商品明细、asid 如何随请求指定。
- 下方 raw.get("xxx") 的键名按公开样例假设，落地前用真实响应逐一核对。
"""

import hashlib
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from backend.core.errors import ApiError

EXTERNAL_SYSTEM = "lemon-open2"
INVOICE_CATEGORY_INPUT = 10080  # 进项发票

STATUS_MAP = {"正常": "normal", "已红冲": "red_offset", "作废": "void"}


def _dec(value: Any, label: str) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ApiError(422, f"{label}不是有效数值") from None


def _date(value: Any, label: str) -> Optional[date]:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        # open2 可能返回 YYYY-MM-DD HH:MM:SS，取前 10 位再试。
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise ApiError(422, f"{label}须为日期") from None


def _import_key(asid: str, record_id: str) -> str:
    return hashlib.sha256(f"{asid}:{record_id}".encode("utf-8")).hexdigest()


def map_invoice(raw: dict, *, tenant: str, asid: str, now) -> dict:
    """一张 open2 进项发票票头 -> invoices 表一行（storage 就绪 dict）。"""
    record_id = str(raw.get("invoiceID") or raw.get("fphm") or "")
    if not record_id:
        raise ApiError(422, "柠檬云发票缺少稳定记录 ID（invoiceID/fphm）")
    head = {
        "tenant_id": tenant,
        "external_system": EXTERNAL_SYSTEM,
        "external_account": asid,
        "external_record_id": record_id,
        "import_key": _import_key(asid, record_id),
        "source_version": 1,
        "invoice_direction": "input",
        "invoice_type_name": raw.get("fplx"),
        "invoice_code": raw.get("fpdm"),
        "invoice_no": raw.get("sdphm") or raw.get("fphm"),
        "invoice_date": _date(raw.get("kprq"), "开票日期"),
        "invoice_status": STATUS_MAP.get(raw.get("fpzt"), "unknown"),
        "seller_name": raw.get("xfmc"),
        "seller_tax_no": raw.get("xfsbh"),
        "seller_address_phone": raw.get("xfdzdh"),
        "seller_bank_account": raw.get("xfyhzh"),
        "buyer_name": raw.get("gfmc"),
        "buyer_tax_no": raw.get("gfsbh"),
        "amount_excluding_tax": _dec(raw.get("je"), "金额"),
        "tax_amount": _dec(raw.get("se"), "税额"),
        "amount_including_tax": _dec(raw.get("jshj"), "价税合计"),
        "detail_sync_status": "pending",
        "validation_status": "review",
        "validation_errors": [
            {"code": "LEMON_OPEN2_UNVERIFIED", "message": "来源为柠檬云 open2，待核对后再参与匹配"}
        ],
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "synced_at": now,
        "source_data": {
            "schema_version": 1,
            "source_kind": "lemon_open2_getinvoice",
            "account_id": asid,
            "raw": raw,
        },
    }
    return head


def map_lines(details: list, *, tenant: str, now) -> list:
    """一组 open2 商品明细 -> invoice_lines 表多行（不含 invoice_id，由 DAO 关联）。"""
    lines = []
    for index, d in enumerate(details, 1):
        lines.append(
            {
                "tenant_id": tenant,
                "source_line_key": f"{index}",  # 稳定组合待实测确认后替换（见设计文档 §4.4）
                "line_no": str(index),
                "item_name": d.get("mc"),
                "specification": d.get("ggxh"),
                "unit_name": d.get("jldw"),
                "quantity": _dec(d.get("sl"), "数量"),
                "unit_price": _dec(d.get("dj"), "单价"),
                "amount_excluding_tax": _dec(d.get("je"), "金额"),
                "tax_rate_raw": d.get("slv"),
                "tax_amount": _dec(d.get("se"), "税额"),
                "amount_including_tax": _dec(d.get("jshj"), "价税合计"),
                "synced_at": now,
                "is_active": True,
            }
        )
    return lines
