"""快照字段搜索表达式；不查询实时来源，筛选后再聚合与分页。"""

import json

from sqlalchemy import case, func, or_, select

from backend.core.search_terms import search_terms

from ..entity.declaration_snapshot import declaration_snapshots as snapshots
from ..entity.snapshot_supplier import snapshot_suppliers as suppliers


def conditions(query, dialect):
    result = []
    if query.supplierName:
        result.append(
            snapshots.c.customs_declaration_id.in_(
                select(suppliers.c.declaration_id).where(
                    or_(
                        *(
                            suppliers.c.name.contains(term, autoescape=True)
                            for term in search_terms(query.supplierName)
                        )
                    )
                )
            )
        )
    if query.recordNo:
        record = text_field("$.recordNumber", dialect)
        result.append(or_(*(record.contains(term, autoescape=True) for term in search_terms(query.recordNo))))
    if query.declarationNo:
        result.append(
            or_(
                *(
                    text_field("$.declaration", dialect).contains(term, autoescape=True)
                    for term in search_terms(query.declarationNo)
                )
            )
        )
    if query.purchaseOrderNo:
        result.append(order_matches(search_terms(query.purchaseOrderNo), dialect))
    return result


def text_field(path, dialect):
    """快照 payload 中的文本字段；MySQL 需去掉 JSON 引号。"""
    value = func.json_extract(snapshots.c.payload, path)
    return func.json_unquote(value) if dialect == "mysql" else value


def margin_status_matches(status, dialect):
    """精确匹配报关行已有的幅度状态，不搜索原因文案或子采购行。"""
    lines = func.json_extract(snapshots.c.payload, "$.customsLines")
    if dialect == "mysql":
        return func.json_contains(lines, json.dumps({"marginStatus": status})) == 1
    entries = func.json_each(lines).table_valued("value", joins_implicitly=True)
    return (
        select(1)
        .select_from(entries)
        .where(func.json_extract(entries.c.value, "$.marginStatus") == status)
        .correlate(snapshots)
        .exists()
    )


def order_matches(terms, dialect):
    # v3 投影保存所有关联子单，包括无明细子单。旧快照补算期间兼容原展示字段。
    numbers = func.json_extract(snapshots.c.payload, "$.purchaseOrderNumbers")
    if dialect == "mysql":
        matches = []
        for term in terms:
            pattern = "%" + term.replace("/", "//").replace("%", "/%").replace("_", "/_") + "%"
            matches.append(
                case(
                    (numbers.is_not(None), func.json_search(numbers, "one", pattern, "/").is_not(None)),
                    else_=func.json_search(
                        snapshots.c.payload,
                        "one",
                        pattern,
                        "/",
                        "$**.child",
                        "$.currencyChecks[*].orderNumber",
                    ).is_not(None),
                )
            )
        return or_(*matches)
    entries = func.json_each(numbers).table_valued("value", joins_implicitly=True)
    current = (
        select(1)
        .select_from(entries)
        .where(or_(*(entries.c.value.contains(term, autoescape=True) for term in terms)))
        .correlate(snapshots)
        .exists()
    )
    tree = func.json_tree(snapshots.c.payload).table_valued("key", "value", joins_implicitly=True)
    legacy = (
        select(1)
        .select_from(tree)
        .where(
            tree.c.key.in_(["child", "orderNumber"]),
            or_(*(tree.c.value.contains(term, autoescape=True) for term in terms)),
        )
        .correlate(snapshots)
        .exists()
    )
    return case((numbers.is_not(None), current), else_=legacy)
