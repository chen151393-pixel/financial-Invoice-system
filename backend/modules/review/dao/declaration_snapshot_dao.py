"""财务查询快照：仅操作 review 表，在数据库筛选、聚合和分页。"""

from sqlalchemy import and_, case, delete, func, insert, select

from ..entity.calculation_job import calculation_jobs as jobs
from ..entity.declaration_snapshot import declaration_snapshots as snapshots
from ..entity.snapshot_supplier import snapshot_suppliers as suppliers


def replace_account(connection, account, rows, supplier_rows):
    # 只替换可重建的查询投影，审核记录、冻结依据和来源数据保持不变。
    connection.execute(delete(suppliers).where(suppliers.c.ns_account == account))
    connection.execute(delete(snapshots).where(snapshots.c.ns_account == account))
    for start in range(0, len(rows), 100):
        connection.execute(insert(snapshots), rows[start : start + 100])
    for start in range(0, len(supplier_rows), 300):
        connection.execute(insert(suppliers), supplier_rows[start : start + 300])


def browse(connection, query, key, month_start):
    fresh = and_(jobs.c.requested_revision == jobs.c.completed_revision, jobs.c.calculation_key == key)
    pending = snapshots.c.review_status == "pending"
    approved = snapshots.c.review_status == "approved"
    alert = and_(pending, fresh, snapshots.c.margin_alert.is_(True))
    auto = and_(pending, fresh, snapshots.c.auto_eligible.is_(True))
    conditions = []
    if query.account:
        conditions.append(snapshots.c.ns_account == query.account)
    if query.keyword:
        conditions.append(snapshots.c.search_text.contains(query.keyword, autoescape=True))
    if query.supplierId:
        conditions.append(
            snapshots.c.customs_declaration_id.in_(
                select(suppliers.c.declaration_id).where(suppliers.c.supplier_id == int(query.supplierId))
            )
        )
    joined = snapshots.join(jobs, jobs.c.ns_account == snapshots.c.ns_account)
    aggregate = {"all": func.count()}
    for name, condition in {
        "pending": pending,
        "approved": approved,
        "changed": and_(pending, snapshots.c.source_changed.is_(True)),
        "approvedThisMonth": and_(approved, snapshots.c.approved_at >= month_start),
        "marginAlert": alert,
        "autoApprovable": auto,
    }.items():
        aggregate[name] = func.coalesce(func.sum(case((condition, 1), else_=0)), 0)
    counts = dict(
        connection.execute(
            select(*[expression.label(name) for name, expression in aggregate.items()])
            .select_from(joined)
            .where(*conditions)
        )
        .mappings()
        .one()
    )
    # MySQL SUM(CASE...) 返回 Decimal；这里是计数，不是金额，统一转为接口整数。
    counts = {name: int(value) for name, value in counts.items()}
    selected = {"pending": pending, "approved": approved, "margin_alert": alert, "auto": auto}
    if query.status in selected:
        conditions.append(selected[query.status])
    total = counts[{"margin_alert": "marginAlert", "auto": "autoApprovable"}.get(query.status, query.status)]
    page = list(
        connection.execute(
            select(
                snapshots.c.payload,
                snapshots.c.calculated_at,
                fresh.label("fresh"),
                jobs.c.last_error,
            )
            .select_from(joined)
            .where(*conditions)
            .order_by(snapshots.c.declaration_date.desc(), snapshots.c.customs_declaration_id.desc())
            .limit(query.pageSize)
            .offset((query.page - 1) * query.pageSize)
        ).mappings()
    )
    supplier_query = select(suppliers.c.supplier_id, suppliers.c.name).distinct()
    if query.account:
        supplier_query = supplier_query.where(suppliers.c.ns_account == query.account)
    options = list(
        connection.execute(supplier_query.order_by(suppliers.c.name, suppliers.c.supplier_id)).mappings()
    )
    job_rows = list(connection.execute(select(jobs).order_by(jobs.c.ns_account)).mappings())
    return counts, total, page, options, job_rows
