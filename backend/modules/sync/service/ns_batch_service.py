"""NS 定时计划批次查询：执行记录分页与单批分页明细、执行中阶段进度。"""

import hashlib

from backend.core.errors import ApiError

from ..dao import ns_plan_dao as plans
from ..dao import ns_run_dao as pages
from ..dao import sync_run_dao as runs
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
        with self.engine.connect() as connection:
            rows, total = runs.list_page(connection, scope, page, size, phase)
            counts = runs.counts(connection, scope)
            plan = plan_view(plans.get(connection, scope))
        return {
            "items": [batch_view(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": size,
            "pages": max(1, (total + size - 1) // size),
            "counts": counts,
            "plan": {"enabled": plan["enabled"], "nextRunAt": plan["nextRunAt"]},
        }

    def read(self, owner, request_id):
        self.require_admin(owner)
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
