"""财务核对工作台状态：复用审核摘要、出库准入和全局依据待复核规则。"""

from backend.modules.source.public import admission_issues

from ..dao import purchase_basis_dao, review_record_dao
from ..policy.review_policy import CHANGED_WARNING, status


def workbench_reviews(connection, declarations):
    """待财务核对的报关单；已审核通过和未出库的不进入待办。"""
    active = review_record_dao.active_by_declarations(connection, [row["id"] for row in declarations])
    required = purchase_basis_dao.required_declarations(connection, [row["id"] for row in active.values()])
    result = []
    for row in declarations:
        record = active.get(row["id"])
        admission = admission_issues(row["declaration_no"], row["order_count"])
        state, changed = status(
            row["content_sha256"], admission, record, bool(record) and record["id"] in required
        )
        if state != "pending":
            continue
        result.append(
            {
                **row,
                "review_state": state,
                # 已审核后来源变化、需重新审核
                "changed": changed,
                "reason": CHANGED_WARNING if changed else "核对报关与关联子采购后，整单审核",
            }
        )
    return result
