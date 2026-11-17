"""工作台业务流程漏斗与开票任务节点分布（纯函数）。

报关单所处位置：待财务审核为 pending_review；审核通过后取其当前任务中最慢的开票跟进节点（与任务台同一判定），
任务全部完成为 done；审核通过但没有任务（供应商均关闭通知）为"无需开票"，不进漏斗。
漏斗每一步为"至少走到这一步"的报关单数，卡点为停在上一步与这一步之间的报关单。
"已通知供应商"按发送记录计算：节点已越过通知（未通知即收票）但有任务没有发送记录的报关单不计入，
单列为"未通知即收票"；其后一步的通过率仍相对按位置走到通知之后的报关单数计算。
"""

from collections import Counter, defaultdict
from decimal import Decimal

from backend.modules.task.public import NODE_LABELS, NODES

from .workbench_reports import percent

# 位置顺序：待审核 → 开票跟进各节点（documents … completion）→ 完结 done
POSITIONS = ("pending_review", *NODES)
POSITION_LABELS = {"pending_review": "待财务审核", **NODE_LABELS}

SKIPPED_NOTIFY = {"key": "notification_skipped", "label": "未通知即收票"}

# (步骤键, 文字, 到达这一步须越过的位置)；最后一步要求位置为 done
FLOW = (
    ("synced", "已入库待开票报关单", None),
    ("approved", "财务审核通过", "pending_review"),
    ("archived", "子采购合同归档", "documents"),
    ("notified", "已通知供应商", "notification"),
    ("invoiced", "已收到发票", "invoices"),
    ("completed", "资料齐全完结", "completion"),
)


def declaration_positions(declarations, pending_ids, tasks, scope, admitted):
    """返回 (各位置的报关单数 Counter, 无需开票张数)。admitted(row) 判断报关单是否已出库。

    Counter 另含 notification_skipped：位置已越过通知、但有任务没有发送记录的报关单数（不属于任何位置）。
    """
    nodes, unnotified = defaultdict(list), set()
    for task in tasks:
        nodes[task["customs_declaration_id"]].append(task["node"])
        if not task.get("notified", True):
            unnotified.add(task["customs_declaration_id"])
    counts, none = Counter(), 0
    beyond = POSITIONS.index("notification")
    for row in declarations:
        if not admitted(row) or not scope.declaration(row):
            continue
        if row["id"] in pending_ids:
            counts["pending_review"] += 1
        elif nodes.get(row["id"]):
            position = min(nodes[row["id"]], key=POSITIONS.index)
            counts[position] += 1
            if row["id"] in unnotified and POSITIONS.index(position) > beyond:
                counts[SKIPPED_NOTIFY["key"]] += 1
        else:
            none += 1
    return counts, none


def funnel(positions):
    """六步漏斗：数量、相对上一步的通过率（上一步为 0 时为空）及卡在上一步的位置分项。"""
    skipped = positions[SKIPPED_NOTIFY["key"]]
    total = sum(positions[position] for position in POSITIONS)
    result, previous, passed = [], None, 0
    for key, label, threshold in FLOW:
        if threshold is not None:
            end = POSITIONS.index(threshold) + 1
            stuck = [
                {"key": position, "label": POSITION_LABELS[position], "count": positions[position]}
                for position in POSITIONS[passed:end]
                if positions[position]
            ]
            passed = end
        else:
            stuck = []
        reached = sum(positions[position] for position in POSITIONS[passed:])
        count = reached
        if key == "notified" and skipped:
            count -= skipped
            stuck.append({**SKIPPED_NOTIFY, "count": skipped})
        rate = None if not previous else percent(Decimal(count), Decimal(previous))
        result.append({"key": key, "label": label, "count": count, "rate": rate, "stuck": stuck})
        previous = reached
    return {
        "steps": result,
        "completionRate": percent(Decimal(result[-1]["count"]), Decimal(total)) if total else None,
    }


def node_distribution(tasks):
    """进行中任务（未完成）按开票跟进节点计数与占比。"""
    counts = Counter(task["node"] for task in tasks if task["node"] != "done")
    total = sum(counts.values())
    return {
        "total": total,
        "nodes": [
            {
                "key": key,
                "label": NODE_LABELS[key],
                "count": counts[key],
                "percent": percent(Decimal(counts[key]), Decimal(total)),
            }
            for key in NODES
            if key != "done"
        ],
    }
