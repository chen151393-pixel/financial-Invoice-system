"""工作台任务只读门面：复用跟进金额口径，保留未知金额。"""

from collections import defaultdict
from decimal import Decimal

from backend.modules.source.public import purchase_lines

from ..dao import workbench_task_dao
from ..policy.followup_policy import amounts, waiting
from ..policy.task_policy import STATUS_LABELS, STATUS_REASONS


def workbench_tasks(connection, now):
    tasks, lines = workbench_task_dao.read(connection)
    context = purchase_lines(connection, [line["purchase_line_id"] for line in lines])
    grouped = defaultdict(list)
    for line in lines:
        grouped[line["task_id"]].append(line)
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
                "reason": f"{waiting(task, now)}；{STATUS_REASONS[task['status']]}",
            }
        )
    return result
