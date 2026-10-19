"""财务核对工作台状态：复用审核摘要和全局依据待复核规则。"""

from ..dao import purchase_basis_dao, review_record_dao
from ..policy.review_policy import CHANGED_WARNING, NO_PURCHASE_REASON, status


def workbench_reviews(connection, declarations):
    active = review_record_dao.active_by_declarations(connection, [row["id"] for row in declarations])
    required = purchase_basis_dao.required_declarations(connection, [row["id"] for row in active.values()])
    result = []
    for row in declarations:
        record = active.get(row["id"])
        state, changed = status(row["content_sha256"], row["order_count"], record)
        if record and record["id"] in required:
            state, changed = "pending", True
        if state == "approved":
            continue
        result.append(
            {
                **row,
                "review_state": state,
                "reason": NO_PURCHASE_REASON
                if state == "blocked"
                else CHANGED_WARNING
                if changed
                else "核对报关与关联子采购后，整单审核",
            }
        )
    return result
