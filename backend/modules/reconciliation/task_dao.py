"""开票任务SQL：调用方管理事务，分页和分组统计由数据库执行。"""

from sqlalchemy import func, insert, or_, select, update

from .entity import snapshots
from .task_entity import documents, tasks


def replace_revision(connection, owner, account, declaration_id, values):
    connection.execute(
        update(tasks)
        .where(
            tasks.c.owner == owner,
            tasks.c.account == account,
            tasks.c.declaration_id == declaration_id,
            tasks.c.status != "superseded",
        )
        .values(status="superseded")
    )
    if values:
        connection.execute(insert(tasks), values)


def count_snapshot(connection, owner, snapshot_id):
    return connection.execute(
        select(func.count())
        .select_from(tasks)
        .where(
            tasks.c.owner == owner,
            tasks.c.snapshot_id == snapshot_id,
        )
    ).scalar_one()


def browse(connection, owner, query):
    if connection.dialect.name == "sqlite":
        # SQLite旧事务模式的SELECT不会自动BEGIN；显式开启，直到Service关闭连接释放快照。
        connection.exec_driver_sql("BEGIN")
    criteria = [tasks.c.owner == owner]
    if query.status == "current":
        criteria.append(tasks.c.status != "superseded")
    elif query.status == "superseded":
        criteria.append(tasks.c.status == "superseded")
    if query.account:
        criteria.append(tasks.c.account == query.account)
    if query.keyword.strip():
        criteria.append(
            or_(
                *(
                    column.contains(query.keyword.strip(), autoescape=True)
                    for column in (
                        tasks.c.record_number,
                        tasks.c.supplier,
                        tasks.c.company,
                    )
                )
            )
        )
    group_column = tasks.c.supplier_key if query.groupBy == "supplier" else tasks.c.declaration_key
    grouped = (
        select(group_column.label("key"), func.max(tasks.c.created_at).label("latest"))
        .where(*criteria)
        .group_by(group_column)
    )
    total = connection.execute(select(func.count()).select_from(grouped.subquery())).scalar_one()
    keys = list(
        connection.execute(
            grouped.order_by(func.max(tasks.c.created_at).desc(), group_column)
            .offset((query.page - 1) * query.pageSize)
            .limit(query.pageSize)
        ).mappings()
    )
    rows = (
        list(
            connection.execute(
                select(tasks)
                .where(*criteria, group_column.in_([row["key"] for row in keys]))
                .order_by(tasks.c.created_at.desc(), tasks.c.id)
            ).mappings()
        )
        if keys
        else []
    )
    counts = dict(
        connection.execute(
            select(tasks.c.status, func.count()).where(*criteria).group_by(tasks.c.status)
        ).all()
    )
    accounts = list(
        connection.execute(
            select(tasks.c.account).where(tasks.c.owner == owner).distinct().order_by(tasks.c.account)
        ).scalars()
    )
    return keys, rows, counts, accounts, total


def detail(connection, owner, task_id, *, lock=False):
    statement = (
        select(tasks, snapshots.c.digest, snapshots.c.payload.label("snapshot_payload"))
        .join(snapshots, snapshots.c.id == tasks.c.snapshot_id)
        .where(tasks.c.owner == owner, tasks.c.id == task_id)
    )
    return connection.execute(statement.with_for_update() if lock else statement).mappings().first()


def document_rows(connection, task_id):
    return list(
        connection.execute(
            select(*[column for column in documents.c if column.name != "content"]).where(
                documents.c.task_id == task_id
            )
        ).mappings()
    )


def document_file(connection, task_id, order_id):
    return (
        connection.execute(
            select(documents).where(documents.c.task_id == task_id, documents.c.order_id == order_id)
        )
        .mappings()
        .first()
    )


def save_document(connection, values):
    connection.execute(insert(documents).values(**values))


def archive_document(connection, task_id, order_id, path, filename, at, complete):
    connection.execute(
        update(documents)
        .where(
            documents.c.task_id == task_id,
            documents.c.order_id == order_id,
            documents.c.archived_at.is_(None),
        )
        .values(archive_path=path, filename=filename, archived_at=at)
    )
    if complete:
        connection.execute(
            update(tasks)
            .where(tasks.c.id == task_id, tasks.c.status == "documents_pending")
            .values(status="notify_pending")
        )
