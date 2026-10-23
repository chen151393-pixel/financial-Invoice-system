"""子采购行比对上下文（经 public.py 暴露给 matching，需传入调用方的数据库连接）。

line_digest 覆盖比对用到的全部来源字段：建议生成后子采购行或币种变化时，摘要改变，比对依据过期。
"""

import hashlib
import json

from ..dao import purchase_order_dao
from ..policy.content_digest import canonical

FIELDS = (
    "ns_account",
    "supplier_id",
    "company_id",
    "parent_order_id",
    "parent_relation_status",
    "source_line_key",
    "purchase_order_id",
    "order_no",
    "parent_order_no",
    "supplier_name",
    "supplier_name_normalized",
    "company_name",
    "company_name_normalized",
    "item_name",
    "declaration_name",
    "item_name_normalized",
    "specification",
    "quantity",
    "unit",
    "amount",
    "currency",
    "currency_source",
    "currency_issue",
)


def line_digest(context):
    content = {key: canonical(context[key]) for key in FIELDS} | {"active": context["active"]}
    return hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def supplier_line_ids(connection, supplier_id):
    """该供应商的子采购行 ID，供比对队列按供应商筛选。"""
    return purchase_order_dao.line_ids_by_supplier(connection, supplier_id)


def purchase_lines(connection, line_ids, *, lock=False):
    """{子采购行 ID: 比对上下文}；active 为子采购单与行均有效。"""
    result = {}
    for row in purchase_order_dao.line_context(connection, sorted(set(line_ids)), lock=lock):
        context = {key: row[key] for key in FIELDS}
        context["active"] = bool(row["is_active"] and row["order_active"])
        context["digest"] = line_digest(context)
        context["source_refs"] = {
            "purchase_raw_record_id": row["raw_record_id"],
            "currency_raw_record_id": row["currency_raw_record_id"],
        }
        result[row["id"]] = context
    return result
