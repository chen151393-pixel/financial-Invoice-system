"""子采购行比对上下文（经 public.py 暴露给 matching，需传入调用方的数据库连接）。

line_digest 覆盖比对用到的全部来源字段：建议生成后子采购行或币种变化时，摘要改变，比对依据过期。
"""

import hashlib
import json

from ..dao import purchase_order_dao
from ..dao.unit_dictionary_dao import unit_names
from ..policy.content_digest import canonical
from ..policy.unit_policy import unit_label
from .declared_price_reader import declared_prices

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


def supplier_line_ids(connection, supplier_id=None, *, name_terms=()):
    """按供应商 ID 或名称部分匹配获取子采购行 ID；多名称取并集，与 ID 取交集。"""
    return purchase_order_dao.line_ids_by_supplier(connection, supplier_id, name_terms=name_terms)


def purchase_lines(connection, line_ids, *, lock=False):
    """{子采购行 ID: 比对上下文}；active 为子采购单与行均有效。"""
    result = {}
    names = unit_names(connection)
    for row in purchase_order_dao.line_context(connection, sorted(set(line_ids)), lock=lock):
        context = {key: row[key] for key in FIELDS}
        context["active"] = bool(row["is_active"] and row["order_active"])
        context["digest"] = line_digest(context)
        # NS 单位存编号，比对须用字典名称；不参与摘要，字典调整不会使已有建议过期
        context["unit_name"] = unit_label(row["unit"], names)
        # 税率供发票整单比对核对税额；不参与摘要，补同步税率不会使已有建议过期
        context["tax_rate"] = row["tax_rate"]
        # 对应报关行的人民币申报价（价格校验用）；只读参考，不参与摘要
        context["declared"] = None
        context["source_refs"] = {
            "purchase_raw_record_id": row["raw_record_id"],
            "currency_raw_record_id": row["currency_raw_record_id"],
        }
        result[row["id"]] = context
    for line_id, declared in declared_prices(connection, list(result)).items():
        result[line_id]["declared"] = declared
    return result


def line_declarations(connection, line_ids):
    """子采购行所属子采购单号与报关单 ID，供 matching 归档发票文件时确定报关单文件夹。"""
    return purchase_order_dao.line_declarations(connection, line_ids)
