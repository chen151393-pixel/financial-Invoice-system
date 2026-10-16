"""同步时读取子采购单关联的母采购单头（币种、汇率）；只读 NS，在数据库事务之外调用。"""

from backend.core.errors import ApiError

from ..mapper.ns_fields import reference
from ..policy.parent_reference_policy import PARENT_FIELD

BATCH = 300


def parent_ids(bundle):
    return sorted({reference(head.get(PARENT_FIELD)) for _, head, _ in bundle["purchases"]} - {""})


def read_parent_orders(ns, bundle):
    """返回 {母采购单 NS ID: 单头}；任何批次失败都整页失败，不保存部分结果。"""
    ids = parent_ids(bundle)
    headers = {}
    for start in range(0, len(ids), BATCH):
        batch = ids[start : start + BATCH]
        for row in ns.relation_rows("parent_headers", batch):
            identity = str(row.get("id") or "")
            if identity not in batch or identity in headers:
                raise ApiError(502, "母采购单头返回范围不一致或身份重复，未保存本页")
            headers[identity] = row
    return headers
