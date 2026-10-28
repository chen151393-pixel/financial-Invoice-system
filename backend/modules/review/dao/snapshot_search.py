"""快照字段搜索表达式；不查询实时来源，筛选后再聚合与分页。"""

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
        record = func.json_extract(snapshots.c.payload, "$.recordNumber")
        if dialect == "mysql":
            record = func.json_unquote(record)
        result.append(or_(*(record.contains(term, autoescape=True) for term in search_terms(query.recordNo))))
    if query.purchaseOrderNo:
        result.append(order_matches(search_terms(query.purchaseOrderNo), dialect))
    return result


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
