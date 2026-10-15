"""供其他模块在同一事务中读取有效任务行（经 public.py 暴露）。"""

from ..dao import task_dao, task_line_dao


def open_lines(connection, purchase_line_ids=None, *, lock=False):
    if lock and purchase_line_ids:
        found = task_line_dao.active_by_purchase_lines(connection, purchase_line_ids)
        task_dao.by_ids(connection, sorted({line["task_id"] for line in found}), lock=True)
        task_line_dao.active_by_purchase_lines(connection, purchase_line_ids, lock=True)
    return task_dao.open_lines(connection, purchase_line_ids)
