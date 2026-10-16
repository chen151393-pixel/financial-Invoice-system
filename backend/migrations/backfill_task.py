"""0007 回填：保留旧进度为待复核占用，原完成历史不删除。"""

from sqlalchemy import MetaData, Table, select, update


def backfill(connection):
    meta = MetaData()
    lines = Table("task_lines", meta, autoload_with=connection)
    reviews = Table("review_lines", meta, autoload_with=connection)
    tasks = Table("task_tasks", meta, autoload_with=connection)
    events = Table("task_events", meta, autoload_with=connection)
    bases = {
        r.id: r.purchase_basis_id
        for r in connection.execute(select(reviews.c.id, reviews.c.purchase_basis_id))
    }
    affected = set()
    for row in connection.execute(select(lines)).mappings():
        values = {"purchase_basis_id": bases.get(row["review_line_id"])}
        if row["status"] != "superseded":
            values.update(
                requires_review=True,
                pending_quantity=row["received_quantity"],
                pending_amount=row["received_amount"],
                received_quantity=0,
                received_amount=0,
                closed_with_difference=False,
                status="open",
            )
            affected.add(row["task_id"])
        connection.execute(update(lines).where(lines.c.id == row["id"]).values(**values))
    for task in connection.execute(select(tasks).where(tasks.c.id.in_(affected))).mappings():
        target = (
            "awaiting_invoice" if task["status"] in ("completed", "partially_received") else task["status"]
        )
        connection.execute(
            events.insert().values(
                task_id=task["id"],
                from_status=task["status"],
                to_status=target,
                event_type="migration_review_required",
                reason="历史依据需重新核实；已收数额保留为待复核占用",
                actor="migration",
                occurred_at=task["updated_at"],
                created_at=task["updated_at"],
                updated_at=task["updated_at"],
            )
        )
        connection.execute(update(tasks).where(tasks.c.id == task["id"]).values(status=target))
