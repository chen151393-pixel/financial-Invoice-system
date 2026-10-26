"""同步时读取子采购单对应的销售单头（币种、汇率）；只读 NS，在数据库事务之外调用。

只用于申报幅度与发票价格校验，不影响单据保存：读取失败时记录提示并跳过，已保存的汇率保持不变。
"""

import logging

from backend.core.errors import ApiError

from ..mapper.ns_fields import reference

SALES_FIELD = "custrecord_swc_subpo_so"
BATCH = 300
WARNING = "销售单汇率读取失败，申报幅度与价格校验暂无法计算；不影响单据保存，可稍后重新同步"
logger = logging.getLogger("ns_api.source")


def sales_ids(bundle):
    return sorted({reference(head.get(SALES_FIELD)) for _, head, _ in bundle["purchases"]} - {""})


def read_sales_orders(ns, bundle):
    """返回 {销售单 NS ID: 单头}；读取失败返回 None（调用方保留原关联，不清空）。"""
    ids = sales_ids(bundle)
    headers = {}
    try:
        for start in range(0, len(ids), BATCH):
            batch = ids[start : start + BATCH]
            for row in ns.relation_rows("sales_headers", batch):
                identity = str(row.get("id") or "")
                if identity in batch and identity not in headers:
                    headers[identity] = row
    except ApiError as error:
        logger.warning("sales_headers_failed status=%s", error.status)
        bundle["warnings"].append(WARNING)
        return None
    return headers
