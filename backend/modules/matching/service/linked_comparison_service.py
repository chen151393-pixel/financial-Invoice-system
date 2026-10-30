"""已关联整单的只读详情，沿用审核时比对与整单应开快照，不以收票后剩余量重算。"""

from decimal import Decimal

from ..policy.order_group_policy import order_share
from ..policy.pending_order_policy import whole_order
from ..vo.matching_vo import Capability
from .group_comparison_view import comparison_view
from .group_view_service import group_id


def grouped(rows):
    groups = {}
    for row in sorted(rows, key=lambda value: value["id"]):
        if group_id(row):
            groups.setdefault(group_id(row), []).append(row)
    # 部分取消、待复核或没有完整整单证据时，仍逐条展示；不能冒充完整已关联整单。
    return {
        key: own
        for key, own in groups.items()
        if all(
            row["status"] == "confirmed" and row["verification_status"] == "valid" and whole_order(row)
            for row in own
        )
    }


def views(rows, row_views, lines):
    result = []
    for key, own in grouped(rows).items():
        if any(row["purchase_line_id"] not in lines for row in own):
            continue
        compared = {}
        for item_id in dict.fromkeys(row["invoice_item_id"] for row in own):
            parts = [row for row in own if row["invoice_item_id"] == item_id]
            first = row_views[parts[0]["id"]]
            compared[item_id] = (
                [check.model_dump() for check in first.checks],
                Decimal(first.confidence) if first.confidence is not None else None,
                [{**row, "quantity": order_share(row)[0], "amount": order_share(row)[1]} for row in parts],
            )
        result.append(
            comparison_view(
                key,
                own,
                compared,
                lines,
                [],
                Capability(reason="已关联整单，仅展示审核时比对结果"),
                Capability(reason="已通过的关联不能再次驳回"),
            )
        )
    return result
