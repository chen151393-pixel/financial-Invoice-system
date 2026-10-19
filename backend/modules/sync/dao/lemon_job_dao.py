"""账套分片与对应原子请求联查。"""

from sqlalchemy import and_, insert, select, update

from ..entity.lemon_job import lemon_jobs as table
from ..entity.lemon_run import lemon_runs
from ..entity.sync_run import sync_runs


def create(connection, values):
    if values:
        connection.execute(insert(table), values)


def list_jobs(connection, run_id):
    query = (
        select(table, lemon_runs.c.result, lemon_runs.c.status.label("saved_status"))
        .join(sync_runs, table.c.run_id == sync_runs.c.id)
        .outerjoin(
            lemon_runs,
            and_(
                table.c.request_id == lemon_runs.c.request_id, sync_runs.c.scope_key == lemon_runs.c.scope_key
            ),
        )
        .where(table.c.run_id == run_id)
        .order_by(table.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def change(connection, job_id, status, now, error=None):
    connection.execute(
        update(table).where(table.c.id == job_id).values(status=status, error=error, updated_at=now)
    )


def get(connection, job_id):
    row = connection.execute(select(table).where(table.c.id == job_id).with_for_update()).mappings().first()
    return dict(row) if row else None
