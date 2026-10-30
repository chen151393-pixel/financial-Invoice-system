"""合并当前身份手动分页与当前账套计划批次，在数据库中排序、筛选和分页。"""

from sqlalchemy import case, func, literal, select, union_all

from ..entity.ns_run import ns_runs
from ..entity.sync_run import sync_runs


def list_page(connection, scope, manual_scope, executing, page, size, phase=None):
    # 展示状态由 service 提供执行集合；进程遗留 running 不再计为执行中。
    manual_phase = case(
        (ns_runs.c.status == "interrupted", "unknown"),
        ((ns_runs.c.status == "running") & ns_runs.c.request_id.not_in(executing), "unknown"),
        else_=ns_runs.c.status,
    )
    records = union_all(
        select(
            sync_runs.c.id,
            literal("plan").label("record_type"),
            sync_runs.c.phase,
            sync_runs.c.started_at.label("started_at"),
        ).where(sync_runs.c.scope_key == scope),
        select(ns_runs.c.id, literal("manual"), manual_phase, ns_runs.c.created_at).where(
            ns_runs.c.scope_key == manual_scope, ns_runs.c.run_id.is_(None)
        ),
    ).subquery()
    counts = dict(connection.execute(select(records.c.phase, func.count()).group_by(records.c.phase)).all())
    filtered = select(records)
    if phase:
        filtered = filtered.where(records.c.phase == phase)
    total = connection.scalar(select(func.count()).select_from(filtered.subquery()))
    selected = (
        connection.execute(
            filtered.order_by(records.c.started_at.desc(), records.c.record_type, records.c.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        .mappings()
        .all()
    )
    details = {}
    for record_type, table in (("plan", sync_runs), ("manual", ns_runs)):
        ids = [row["id"] for row in selected if row["record_type"] == record_type]
        if ids:
            for row in connection.execute(select(table).where(table.c.id.in_(ids))).mappings():
                details[record_type, row["id"]] = dict(row)
    return [(row["record_type"], details[row["record_type"], row["id"]]) for row in selected], total, counts
