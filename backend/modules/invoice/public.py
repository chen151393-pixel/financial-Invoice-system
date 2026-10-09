"""匹配用例在同一事务中锁定并读取发票，不暴露私有表。"""

import hashlib

from backend.core.errors import ApiError

from .dao import invoice_detail, lock_invoice
from .entity import load_tables
from .vo import invoice_detail_view


def matching_invoice(connection, invoice_id, owner):
    tenant = hashlib.sha256(owner.encode()).hexdigest()
    head, lines = load_tables(connection)
    lock_invoice(connection, head, tenant, invoice_id)
    record, details = invoice_detail(connection, head, lines, tenant, invoice_id)
    if record is None:
        raise ApiError(404, "发票不存在或当前身份无权查看")
    result = invoice_detail_view(record, details)
    result["sourceComplete"] = record.get("detail_sync_status") == "complete"
    result["sourceStatus"] = record["invoice_status"]
    return result
