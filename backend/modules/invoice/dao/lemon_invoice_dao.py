"""API 来源身份核对，防止同来源改票号及跨来源重复占用。"""

from sqlalchemy import select

from ..entity import headers


def source_keys(connection, account, external_ids):
    rows = connection.execute(
        select(headers.c.external_id, headers.c.invoice_key).where(
            headers.c.lemon_account == account,
            headers.c.source == "lemon_open2",
            headers.c.external_id.in_(external_ids),
        )
    ).mappings()
    return {row["external_id"]: row["invoice_key"] for row in rows}


def excel_conflicts(connection, keys):
    return connection.scalar(
        select(headers.c.id)
        .where(headers.c.source == "lemon_excel", headers.c.invoice_key.in_(keys))
        .limit(1)
    )


def api_conflict(connection, key):
    return connection.scalar(
        select(headers.c.id).where(headers.c.source == "lemon_open2", headers.c.invoice_key == key).limit(1)
    )
