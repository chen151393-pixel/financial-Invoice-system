"""NS 定时计划批次查询：执行记录分页与单批分页明细、执行中阶段进度。"""

import hashlib

from backend.core.errors import ApiError

from ..dao import ns_history_dao as history
from ..dao import ns_plan_dao as plans
from ..dao import ns_run_dao as pages
from ..dao import sync_run_dao as runs
from ..vo.ns_history_vo import manual_view
from ..vo.ns_plan_vo import batch_view, plan_view


class NsBatchService:
    def __init__(self, engine, ns_runs, require_admin):
        self.engine, self.ns_runs, self.require_admin = engine, ns_runs, require_admin
        self.pulls = ns_runs.pulls

    def scope(self):
        """计划、批次与分页记录按 NS 账户归属；管理员共同管理，不按个人身份拆分。"""
        account = self.pulls.settings.account or ""
        return hashlib.sha256(f"ns-plan\n{account}".encode()).hexdigest()

    def list(self, owner, page=1, size=20, phase=None):
        self.require_admin(owner)
        scope = self.scope()
        manual_scope = self.ns_runs.scope(owner)
        executing = self.ns_runs.executing(manual_scope)
        with self.engine.connect() as connection:
            rows, total, counts = history.list_page(
                connection, scope, manual_scope, executing, page, size, phase
            )
            plan = plan_view(plans.get(connection, scope))
        return {
            "items": [
                manual_view(row, executing) if kind == "manual" else batch_view(row) for kind, row in rows
            ],
            "total": total,
            "page": page,
            "pageSize": size,
            "pages": max(1, (total + size - 1) // size),
            "counts": counts,
            "plan": {"enabled": plan["enabled"], "nextRunAt": plan["nextRunAt"]},
        }

    def read(self, owner, request_id, record_type="plan"):
        self.require_admin(owner)
        if record_type == "manual":
            scope = self.ns_runs.scope(owner)
            executing = self.ns_runs.executing(scope)
            with self.engine.connect() as connection:
                row = pages.get(connection, scope, request_id)
            if not row or row["run_id"] is not None:
                raise ApiError(404, "未找到当前身份和 NS 账户的手动同步记录")
            progress = self.ns_runs.progress(scope, request_id, owner)
            return manual_view(row, executing, detail=True, progress=progress)
        scope = self.scope()
        with self.engine.connect() as connection:
            row = runs.get(connection, scope, request_id)
            if not row:
                raise ApiError(404, "未找到当前 NS 账户的定时同步批次")
            rows = pages.batch_pages(connection, row["id"])
        executing = self.ns_runs.executing(scope)
        running = next((v for v in rows if v["request_id"] in executing), None)
        progress = self.ns_runs.progress(scope, running["request_id"], row["started_by"]) if running else None
        return batch_view(row, rows, executing, progress)
