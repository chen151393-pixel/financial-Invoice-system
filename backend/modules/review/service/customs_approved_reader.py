"""海关当前有效审核的来源 ID；不读取来源明细、不依赖财务审核状态。"""

from backend.modules.source.public import declaration_refs_by_number

from ..dao import customs_approval_dao


def approved_declaration_ids(connection):
    approvals = customs_approval_dao.approved_current_receipts(connection)
    refs = declaration_refs_by_number(connection, sorted({row["declaration_no"] for row in approvals}))
    approved = set()
    for row in approvals:
        matches = refs.get(row["declaration_no"], [])
        if (
            len(matches) == 1
            and matches[0]["id"] == row["customs_declaration_id"]
            and matches[0]["content_sha256"] == row["source_sha256"]
        ):
            approved.add(row["customs_declaration_id"])
    return approved
