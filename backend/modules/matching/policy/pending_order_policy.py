"""待审建议的整单证据要求；已确认记录不追溯改写。"""

from decimal import Decimal, InvalidOperation

REGENERATE = "旧待审建议缺少整单依据，请点击“重新生成建议”后按整单审核"


def whole_order(row):
    """分组及整单应开快照必须齐全，不能用旧分配量冒充整单应开。"""
    checks = row.get("checks") or {}
    group, share = checks.get("group") or {}, checks.get("orderShare") or {}
    if not group.get("id") or not group.get("orderIds"):
        return False
    try:
        values = [Decimal(share[key]) for key in ("quantity", "amount")]
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return False
    return all(value.is_finite() and value > 0 for value in values)


def legacy_ids(rows):
    """同组任一待审行缺少证据，整组都须重新生成，避免保留半组。"""
    pending = [row for row in rows if row["status"] == "proposed"]
    ids = {row["id"] for row in pending if not whole_order(row)}
    groups = {
        (row["invoice_id"], (row["checks"].get("group") or {}).get("id"))
        for row in pending
        if row["id"] in ids and (row.get("checks") or {}).get("group")
    }
    return ids | {
        row["id"]
        for row in pending
        if (row["invoice_id"], ((row.get("checks") or {}).get("group") or {}).get("id")) in groups
    }
