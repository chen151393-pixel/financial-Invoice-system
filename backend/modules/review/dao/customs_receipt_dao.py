"""海关回执头表与明细表的读写；不提交事务、不决定比对结果。"""

from sqlalchemy import and_, func, insert, or_, select, update

from ..entity.customs_receipt import customs_receipt_lines as lines
from ..entity.customs_receipt import customs_receipts as receipts

LINE_FIELDS = (
    "item_no",
    "source_row",
    "hs_code",
    "name",
    "specification",
    "contract_no",
    "tax_type",
    "check_status",
    "deal_unit",
    "deal_quantity",
    "currency",
    "deal_total",
    "usd_fob",
    "legal_unit",
    "legal_quantity",
    "customs_doc",
    "usage_flag",
)


def head(connection, receipt_id, *, lock=False):
    query = select(receipts).where(receipts.c.id == receipt_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def heads_by_numbers(connection, numbers, *, lock=False):
    if not numbers:
        return {}
    query = select(receipts).where(receipts.c.declaration_no.in_(numbers))
    if lock:
        query = query.with_for_update()
    return {row["declaration_no"]: dict(row) for row in connection.execute(query).mappings()}


def insert_head(connection, values, now):
    result = connection.execute(insert(receipts).values(**values, created_at=now, updated_at=now))
    return result.inserted_primary_key[0]


def update_head(connection, receipt_id, values, now):
    connection.execute(update(receipts).where(receipts.c.id == receipt_id).values(**values, updated_at=now))


def insert_lines(connection, receipt_id, revision, rows, now):
    connection.execute(
        insert(lines),
        [
            {
                **{field: row.get(field) for field in LINE_FIELDS},
                "receipt_id": receipt_id,
                "revision": revision,
                "created_at": now,
                "updated_at": now,
            }
            for row in rows
        ],
    )


def current_lines(connection, receipt_ids):
    """各回执当前版本的明细：{回执 ID: [行, ...]}，按项号排序。"""
    if not receipt_ids:
        return {}
    query = (
        select(lines)
        .select_from(
            lines.join(
                receipts, and_(receipts.c.id == lines.c.receipt_id, receipts.c.revision == lines.c.revision)
            )
        )
        .where(lines.c.receipt_id.in_(receipt_ids))
        .order_by(lines.c.receipt_id, lines.c.item_no)
    )
    result = {receipt_id: [] for receipt_id in receipt_ids}
    for row in connection.execute(query).mappings():
        result[row["receipt_id"]].append(dict(row))
    return result


def ids(connection, receipt_ids=None, *, lock=False):
    """全部回执 ID（或给定范围内存在的 ID），按 ID 排序；lock 时锁定对应头行。"""
    query = select(receipts.c.id, receipts.c.declaration_no).order_by(receipts.c.id)
    if receipt_ids is not None:
        query = query.where(receipts.c.id.in_(receipt_ids))
    if lock:
        query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def _conditions(filters):
    conditions = []
    if filters.get("numbers"):
        conditions.append(
            or_(*(receipts.c.declaration_no.contains(n, autoescape=True) for n in filters["numbers"]))
        )
    if filters.get("consignee"):
        conditions.append(receipts.c.consignee.contains(filters["consignee"], autoescape=True))
    if filters.get("export_from"):
        conditions.append(receipts.c.export_date >= filters["export_from"])
    if filters.get("export_to"):
        conditions.append(receipts.c.export_date <= filters["export_to"])
    if filters.get("name"):
        conditions.append(
            receipts.c.id.in_(
                select(lines.c.receipt_id)
                .select_from(
                    lines.join(
                        receipts,
                        and_(receipts.c.id == lines.c.receipt_id, receipts.c.revision == lines.c.revision),
                    )
                )
                .where(lines.c.name.contains(filters["name"], autoescape=True))
            )
        )
    return conditions


def status_counts(connection, filters):
    """按比对状态计数（不含状态筛选）：{状态: 张数}。"""
    query = (
        select(receipts.c.match_status, func.count())
        .where(*_conditions(filters))
        .group_by(receipts.c.match_status)
    )
    return {status: count for status, count in connection.execute(query)}


def item_count(connection, filters):
    """当前版本明细项数合计（不含状态筛选）。"""
    query = (
        select(func.count())
        .select_from(
            lines.join(
                receipts, and_(receipts.c.id == lines.c.receipt_id, receipts.c.revision == lines.c.revision)
            )
        )
        .where(*_conditions(filters))
    )
    return connection.execute(query).scalar_one()


def page(connection, filters, statuses, offset, limit):
    conditions = _conditions(filters)
    if statuses:
        conditions.append(receipts.c.match_status.in_(statuses))
    total = connection.execute(select(func.count()).select_from(receipts).where(*conditions)).scalar_one()
    query = (
        select(receipts)
        .where(*conditions)
        .order_by(receipts.c.export_date.desc(), receipts.c.declaration_no.desc())
        .offset(offset)
        .limit(limit)
    )
    return total, [dict(row) for row in connection.execute(query).mappings()]
