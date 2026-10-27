"""发票匹配状态（纯函数）：进项发票列表的匹配状态筛选、各状态张数与单张发票的比对状态共用一套判定。

判定顺序：
1. 待复核：存在已通过但复核失效的分配（红字、作废的发票也先提示复核，避免待处理的占用被隐藏）；
2. 不参与比对：票面展示状态不是正常（红字、已被红冲、作废、未知）；
3. 已匹配：有效通过的发票行数 ≥ 发票有效行数（有效行数大于 0）；
4. 部分匹配：部分发票行有效通过；
5. 待审核：没有有效通过的行，但有待审核建议；
6. 未匹配：以上都不满足。
"""

STATUSES = ("confirmed", "partial", "proposed", "needs_review", "none", "excluded")
LABELS = {
    "confirmed": "已匹配",
    "partial": "部分匹配",
    "proposed": "待审核",
    "needs_review": "待复核",
    "none": "未匹配",
    "excluded": "不参与比对",
}


def match_status(display_status, allocations, active_item_count):
    """display_status：发票票面展示状态；allocations：该发票的全部分配；返回
    {status, label, proposed, confirmed, best_confidence}。"""
    proposed = [row for row in allocations if row["status"] == "proposed"]
    confirmed_items = {
        row["invoice_item_id"]
        for row in allocations
        if row["status"] == "confirmed" and row["verification_status"] == "valid"
    }
    if any(row["status"] == "confirmed" and row["verification_status"] != "valid" for row in allocations):
        status = "needs_review"
    elif display_status != "normal":
        status = "excluded"
    elif confirmed_items and active_item_count and len(confirmed_items) >= active_item_count:
        status = "confirmed"
    elif confirmed_items:
        status = "partial"
    elif proposed:
        status = "proposed"
    else:
        status = "none"
    return {
        "status": status,
        "label": LABELS[status],
        "proposed": len(proposed),
        "confirmed": len(confirmed_items),
        "best_confidence": max(
            (row["confidence"] for row in proposed if row["confidence"] is not None), default=None
        ),
    }
