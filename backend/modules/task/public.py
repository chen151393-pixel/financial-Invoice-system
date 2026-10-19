"""task 模块对外门面：其他模块唯一可以导入的文件。

open_lines(connection, purchase_line_ids=None, lock=False)
    有效任务行（应开、已收、单位）及所属任务（供应商、采购公司、币种、报关单）。
    purchase_line_ids 为 None 时返回全部未结束（open / partial）的行，供 matching 生成比对建议。
    lock=True 时在调用方事务中按"任务 → 任务行"顺序加锁，供 matching 确认分配时使用。
"""

from .service.task_line_reader import active_line_ids as active_line_ids
from .service.task_line_reader import open_lines
from .service.workbench_reader import workbench_tasks

__all__ = ["open_lines", "workbench_tasks"]

from .service.task_line_reader import related_line_ids as related_line_ids
