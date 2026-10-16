"""0009 回填：已确认分配继续占用额度，缺少历史依据与换算证据时待复核。"""

from sqlalchemy import MetaData, Table, select, update


def backfill(connection):
    meta = MetaData()
    allocations = Table("matching_allocations", meta, autoload_with=connection)
    headers = Table("invoice_headers", meta, autoload_with=connection)
    items = Table("invoice_items", meta, autoload_with=connection)
    versions = {
        r.id: r.current_version_id
        for r in connection.execute(select(headers.c.id, headers.c.current_version_id))
    }
    units = {r.id: r.unit for r in connection.execute(select(items.c.id, items.c.unit))}
    for row in connection.execute(select(allocations)).mappings():
        connection.execute(
            update(allocations)
            .where(allocations.c.id == row["id"])
            .values(
                invoice_version_id=versions.get(row["invoice_id"]),
                invoice_unit=units.get(row["invoice_item_id"]),
                verification_status="needs_review",
                verification_issues=["历史分配缺少开票依据版本和换算证据，原占用保留"],
                verification_history=[
                    {
                        "action": "migration_review_required",
                        "reviewed_by": row["reviewed_by"],
                        "reviewed_at": str(row["reviewed_at"]),
                    }
                ],
            )
        )
