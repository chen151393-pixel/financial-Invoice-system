"""供应商设置：按供应商读取与带版本保存；没有记录视为开启通知。"""

from sqlalchemy import insert, select, update

from ..entity import supplier_settings


def by_suppliers(connection, supplier_ids):
    if not supplier_ids:
        return {}
    query = select(supplier_settings).where(supplier_settings.c.supplier_id.in_(supplier_ids))
    return {row["supplier_id"]: dict(row) for row in connection.execute(query).mappings()}


def disabled(connection, supplier_ids):
    """关闭通知的供应商 ID 集合。"""
    return {key for key, row in by_suppliers(connection, supplier_ids).items() if not row["notify_enabled"]}


def disabled_ids(connection):
    """全部关闭通知的供应商 ID（档案概况计数用）。"""
    query = select(supplier_settings.c.supplier_id).where(supplier_settings.c.notify_enabled.is_(False))
    return list(connection.execute(query).scalars())


def get(connection, supplier_id, *, lock=False):
    query = select(supplier_settings).where(supplier_settings.c.supplier_id == supplier_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def insert_setting(connection, supplier_id, enabled, actor, now):
    connection.execute(
        insert(supplier_settings).values(
            supplier_id=supplier_id,
            notify_enabled=enabled,
            version=1,
            updated_by=actor,
            created_at=now,
            updated_at=now,
        )
    )


def update_setting(connection, supplier_id, enabled, version, actor, now):
    """版本一致才更新；返回是否更新成功。"""
    result = connection.execute(
        update(supplier_settings)
        .where(supplier_settings.c.supplier_id == supplier_id, supplier_settings.c.version == version)
        .values(notify_enabled=enabled, version=version + 1, updated_by=actor, updated_at=now)
    )
    return result.rowcount == 1
