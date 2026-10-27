"""工作台业务流程漏斗与开票任务节点分布（纯函数）。

报关单所处位置：待财务审核为 pending_review；审核通过后取其当前任务中最慢的开票跟进节点（与任务台同一判定），
任务全部完成为 done；审核通过但没有任务（供应商均关闭通知）为"无需开票"，不进漏斗。
漏斗每一步为"至少走到这一步"的报关单数，卡点为停在上一步与这一步之间的报关单。
"""

from collections import Counter, defaultdict
from decimal import Decimal

from backend.modules.task.public import NODE_LABELS, NODES

from .workbench_reports import percent

# 位置顺序：待审核 → 开票跟进各节点（documents … completion）→ 完结 done
POSITIONS = ("pending_review", *NODES)
POSITION_LABELS = {"pending_review": "待财务审核", **NODE_LABELS}

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
    """返回 (各位置的报关单数 Counter, 无需开票张数)。admitted(row) 判断报关单是否已出库。"""
    nodes = defaultdict(list)
    for task in tasks:
        nodes[task["customs_declaration_id"]].append(task["node"])
    counts, none = Counter(), 0
    for row in declarations:
        if not admitted(row) or not scope.declaration(row):
            continue
        if row["id"] in pending_ids:
            counts["pending_review"] += 1
        elif nodes.get(row["id"]):
            counts[min(nodes[row["id"]], key=POSITIONS.index)] += 1
        else:
            none += 1
    return counts, none


def funnel(positions):
    """六步漏斗：数量、相对上一步的通过率（上一步为 0 时为空）及卡在上一步的位置分项。"""
    total = sum(positions.values())
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
        count = sum(positions[position] for position in POSITIONS[passed:])
        rate = None if not previous else percent(Decimal(count), Decimal(previous))
        result.append({"key": key, "label": label, "count": count, "rate": rate, "stuck": stuck})
        previous = count
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
