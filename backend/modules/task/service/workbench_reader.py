"""工作台任务只读门面：复用跟进金额口径，保留未知金额；当前节点与开票跟进任务台同一判定。"""

from collections import defaultdict
from datetime import UTC
from decimal import Decimal

from backend.modules.source.public import purchase_lines

from ..dao import workbench_task_dao
from ..policy.board_policy import NODE_LABELS
from ..policy.followup_policy import amounts
from ..policy.task_policy import OPEN_STATUSES, STATUS_LABELS, STATUS_REASONS
from .board_facts import board_facts


def waiting_days(created_at, now):
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return max(0, (now - created).days)


def workbench_tasks(connection, now):
    tasks, lines = workbench_task_dao.read(connection)
    context = purchase_lines(connection, [line["purchase_line_id"] for line in lines])
    grouped = defaultdict(list)
    for line in lines:
        grouped[line["task_id"]].append(line)
    facts = board_facts(connection, [task for task in tasks if task["status"] in OPEN_STATUSES])
    result = []
    for task in tasks:
        own = grouped[task["id"]]
        sources = [context.get(line["purchase_line_id"], {}) for line in own]
        outstanding, _, _ = amounts(own)
        result.append(
            {
                **task,
                "outstanding": outstanding,
                "received": sum((line["received_amount"] for line in own), Decimal(0)),
                # 应开合计；任一行应开金额缺失时为空，不以部分金额冒充
                "expected": None
                if not own or any(line["expected_amount"] is None for line in own)
                else sum((line["expected_amount"] for line in own), Decimal(0)),
                "supplier": next(
                    (s["supplier_name"] for s in sources if s.get("supplier_name")), "供应商待确认"
                ),
                "orders": sorted({s["order_no"] for s in sources if s.get("order_no")}),
                "status_label": STATUS_LABELS[task["status"]],
                "status_reason": STATUS_REASONS[task["status"]],
                # 未完成任务自生成起的天数；已完成任务为 None
                "waiting_days": waiting_days(task["created_at"], now)
                if task["status"] in OPEN_STATUSES
                else None,
                # 开票跟进节点：未完成任务按事实判定，已完成为 done
                "node": facts[task["id"]]["node"] if task["id"] in facts else "done",
                "node_label": NODE_LABELS[facts[task["id"]]["node"] if task["id"] in facts else "done"],
            }
        )
    return result
