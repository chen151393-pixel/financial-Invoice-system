"""按冻结的开票依据读取实际任务，包含从其他报关单沿用的有效任务。"""

from collections import defaultdict

from ..dao import supplier_setting_dao, task_dao, task_line_dao


def review_task_outcomes(connection, lines):
    if not lines:
        return {}
    task_lines = task_line_dao.active_by_purchase_lines(
        connection, sorted({line["purchase_line_id"] for line in lines})
    )
    active_tasks = {
        task["id"]: task
        for task in task_dao.by_ids(connection, sorted({line["task_id"] for line in task_lines}))
        if task["status"] != "superseded"
    }
    by_basis = {
        (line["purchase_line_id"], line["purchase_basis_id"]): active_tasks[line["task_id"]]
        for line in task_lines
        if line["task_id"] in active_tasks
    }
    suppliers = sorted({line["supplier_id"] for line in lines if line["supplier_id"]})
    muted = supplier_setting_dao.disabled(connection, suppliers)
    results = defaultdict(lambda: {"created": set(), "reused": set(), "muted": 0, "missing": 0})
    for line in lines:
        review_id = line["review_id"]
        result = results[review_id]
        task = by_basis.get((line["purchase_line_id"], line["purchase_basis_id"]))
        if task:
            result["created" if task["review_id"] == review_id else "reused"].add(task["id"])
        elif line["supplier_id"] in muted:
            result["muted"] += 1
        else:
            result["missing"] += 1
    return results
