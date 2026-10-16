"""从持久分配台账修复任务缓存；不修改分配或清除待核实状态。"""

from backend.core.write_lock import transaction
from backend.modules.task.public import active_line_ids

from . import ledger_service


def rebuild(engine, events):
    with transaction(engine) as connection:
        ids = active_line_ids(connection)
        ledger_service.publish(connection, ids, events, "system:rebuild", "按持久台账重新核对收票缓存")
        return len(ids)
