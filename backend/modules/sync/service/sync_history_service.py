"""数据同步中心的合并执行记录：NS（定时批次 + 当前身份手动分页）与柠檬云发票批次一张列表。

只读汇总，复用两边已有的作用域、执行状态与展示规则；排序、筛选、分页在数据库中完成。
"""

from ..dao import lemon_plan_dao, ns_plan_dao
from ..dao import ns_history_dao as history
from ..vo.lemon_batch_vo import batch_view as lemon_view
from ..vo.lemon_batch_vo import plan_view as lemon_plan_view
from ..vo.ns_history_vo import manual_view
from ..vo.ns_plan_vo import batch_view as ns_view
from ..vo.ns_plan_vo import plan_view as ns_plan_view

SOURCE_LABELS = {"ns": "NetSuite", "lemon": "柠檬云发票"}


class SyncHistoryService:
    def __init__(self, engine, ns_batches, lemon_batches):
        self.engine, self.ns, self.lemon = engine, ns_batches, lemon_batches

    def list(self, owner, page=1, size=20, phase=None, source=None):
        # 两个来源的执行记录都只对管理员开放；作用域各自沿用原规则。
        self.ns.require_admin(owner)
        scope = self.ns.scope()
        manual_scope = self.ns.ns_runs.scope(owner)
        executing = self.ns.ns_runs.executing(manual_scope)
        lemon_scope = self.lemon.scope(owner)
        with self.engine.connect() as connection:
            rows, total, counts = history.list_page(
                connection,
                scope,
                manual_scope,
                executing,
                page,
                size,
                phase,
                lemon_scope=lemon_scope,
                source=source,
            )
            ns_plan = ns_plan_view(ns_plan_dao.get(connection, scope))
            lemon_plan = lemon_plan_view(lemon_plan_dao.get(connection, lemon_scope))
        return {
            "items": [self._view(kind, row, executing) for kind, row in rows],
            "total": total,
            "page": page,
            "pageSize": size,
            "pages": max(1, (total + size - 1) // size),
            "counts": counts,
            "plans": {
                "ns": {"enabled": ns_plan["enabled"], "nextRunAt": ns_plan["nextRunAt"]},
                "lemon": {"enabled": lemon_plan["enabled"], "nextRunAt": lemon_plan["nextRunAt"]},
            },
        }

    @staticmethod
    def _view(kind, row, executing):
        if kind == "lemon":
            view = lemon_view(row)
            return {
                **view,
                "source": "lemon",
                "sourceLabel": SOURCE_LABELS["lemon"],
                "recordType": "lemon",
                "kindLabel": "进项发票",
                "rangeLabel": "开票日期",
            }
        view = manual_view(row, executing) if kind == "manual" else ns_view(row)
        return {**view, "source": "ns", "sourceLabel": SOURCE_LABELS["ns"], "rangeLabel": "创建日期"}
