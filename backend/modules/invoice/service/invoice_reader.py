"""供其他模块在同一事务中读取发票（经 public.py 暴露）：返回普通字典，不暴露表结构。"""

from ..dao import header_dao, item_dao
from ..dto.invoice_dto import InvoiceQuery

HEADER_FIELDS = (
    "current_version_id",
    "detail_status",
    "id",
    "invoice_no",
    "invoice_date",
    "status",
    "seller_name",
    "seller_name_normalized",
    "buyer_name",
    "buyer_name_normalized",
    "currency",
    "amount_including_tax",
    "remark",
)
ITEM_FIELDS = (
    "is_active",
    "id",
    "invoice_id",
    "line_no",
    "item_name",
    "item_name_normalized",
    "specification",
    "quantity",
    "unit",
    "amount_including_tax",
    "amount_excluding_tax",
)


def invoice_ids_between(connection, start, end):
    """开票日期在 start—end（含）之间的发票 ID，供比对队列按开票日期筛选。"""
    return header_dao.ids_between(connection, start, end)


def read_invoice_accounts(connection):
    """返回已入库发票的来源账套标识，供同步模块补充账套名称。"""
    return header_dao.accounts(connection)


def read_invoices(connection, invoice_ids):
    """[{发票头字段..., "items": [发票行字段...]}]，按 ID 顺序；不存在的 ID 不返回。"""
    headers = header_dao.by_ids(connection, sorted(set(invoice_ids)))
    grouped = {header["id"]: [] for header in headers}
    for item in item_dao.by_invoices(connection, list(grouped)):
        grouped[item["invoice_id"]].append({key: item[key] for key in ITEM_FIELDS})
    return [
        {**{key: header[key] for key in HEADER_FIELDS}, "items": grouped[header["id"]]} for header in headers
    ]


def lock_invoice(connection, invoice_id):
    """在调用方事务中锁定发票头（加锁顺序：任务行之后、分配之前）；返回是否存在。"""
    return bool(header_dao.by_ids(connection, [invoice_id], lock=True))


def read_invoice_amount_scope(connection, filters, *, after_id=0):
    """复用列表筛选；首次返回全范围票面汇总，每次返回至多 500 张统计票头。"""
    query = InvoiceQuery(**filters)
    totals = header_dao.amounts(connection, query) if after_id == 0 else None
    return totals, header_dao.amount_page(connection, query, after_id, 500)
