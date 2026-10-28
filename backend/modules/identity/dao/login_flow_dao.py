"""飞书登录流程：一次性 state 与结果。"""

from sqlalchemy import delete, insert, select, update

from ..entity import login_flows


def create(connection, values, now):
    connection.execute(insert(login_flows).values(status="pending", created_at=now, updated_at=now, **values))


def by_state(connection, state_hash, *, lock=False):
    query = select(login_flows).where(login_flows.c.state_hash == state_hash)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def latest_for_browser(connection, browser_hash):
    query = (
        select(login_flows)
        .where(login_flows.c.browser_hash == browser_hash)
        .order_by(login_flows.c.id.desc())
        .limit(1)
    )
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def finish(connection, flow_id, status, reason, user_id, now):
    connection.execute(
        update(login_flows)
        .where(login_flows.c.id == flow_id)
        .values(status=status, reason=reason, user_id=user_id, finished_at=now, updated_at=now)
    )


def purge_before(connection, cutoff):
    """清理一天前的流程记录；登录审计另有 identity_audit。"""
    connection.execute(delete(login_flows).where(login_flows.c.created_at < cutoff))
