"""批量登记资格与确认范围摘要；列表和提交共用，不读写数据库。"""

import hashlib
import json

from .notification_policy import batch_record_block


def record_block(row, fact):
    return (
        fact["blocked"]
        or fact.get("record_block", "")
        or batch_record_block(row["status"], fact["notice_status"])
    )


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def member_revision(row, fact):
    return _digest(
        {
            "id": row["id"],
            "status": row["status"],
            "notice": fact["notice_id"],
            "noticeStatus": fact["notice_status"],
            "block": record_block(row, fact),
            "lines": sorted((line["id"], line["purchase_basis_id"]) for line in fact["lines"]),
        }
    )


def group_revision(members):
    return _digest(sorted(members, key=lambda member: int(member[0])))
