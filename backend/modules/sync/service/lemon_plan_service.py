"""计划修改与到期入队；以绑定行锁保证同一时刻只触发一次。"""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from backend.core.errors import ApiError
from backend.modules.invoice.public import lemon_business_type_options, lemon_import_defaults

from ..dao import lemon_binding_dao as bindings
from ..dao import lemon_plan_dao as plans
from ..dao import lemon_run_dao as invoice_runs
from ..dao import sync_run_dao as runs
from ..policy.lemon_batch_policy import ACTIVE, binding_key
from ..policy.schedule_policy import SHANGHAI, next_time
from ..vo.lemon_batch_vo import plan_view


class LemonPlanService:
    def __init__(self, batches):
        self.batches, self.accounts, self.engine = batches, batches.accounts, batches.engine

    def configuration(self, owner):
        scope = self.batches.scope(owner)
        allowed, reason = True, "可提交后台拉取或配置定时计划"
        with self.engine.connect() as connection:
            plan = plan_view(plans.get(connection, scope))
            latest = invoice_runs.latest(connection, scope)
            try:
                self.accounts.context(connection, owner)
            except ApiError as error:
                allowed, reason = False, error.message
        if not plan["businessTypes"]:
            plan["businessTypes"] = lemon_import_defaults()
        return {
            "plan": plan,
            "submit": {"allowed": allowed, "reason": reason},
            "pause": {"allowed": plan["enabled"], "reason": "暂停计划不影响已提交批次"},
            "coverage": "全部账套包含当前绑定账号下的专业版与免费版授权账套；同一账号多个专业版服务的枚举尚未验证。",
            "businessTypeOptions": sorted(
                set(lemon_business_type_options(latest["result"] if latest else None) + plan["businessTypes"])
            ),
            "timezone": "Asia/Shanghai",
        }

    def save(self, owner, body):
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.engine.begin() as connection:
            scope = self.batches.scope(owner)
            binding = bindings.get(connection, scope, lock=True)
            if body.enabled:
                scope, binding = self.accounts.context(connection, owner, lock=True)
            if not binding:
                raise ApiError(409, "请先完成账号绑定")
            previous = plans.get(connection, scope)
            if body.revision != (previous["revision"] if previous else 0):
                raise ApiError(409, "计划已被修改，请刷新后重新编辑")
            config = body.model_dump(exclude={"revision", "enabled"})
            plans.save(
                connection,
                scope,
                {
                    "owner": owner,
                    "enabled": body.enabled,
                    "revision": body.revision + 1,
                    "configuration": {**config, "bindingKey": binding_key(binding)},
                    "next_run_at": next_time(body.times, now) if body.enabled else None,
                    "updated_at": now,
                },
            )
        return self.configuration(owner)

    def tick(self, owner, now=None):
        now = now or datetime.now(UTC).replace(tzinfo=None)
        scope = self.batches.scope(owner)
        with self.engine.connect() as connection:
            # 预检查与写事务分开，避免 MySQL 可重复读持有锁前的旧快照。
            if not plans.due(connection, scope, now):
                return
        with self.engine.begin() as connection:
            _, binding = self.accounts.context(connection, owner, lock=True)
            plan = plans.due(connection, scope, now, lock=True)
            if not plan:
                return
            config = plan["configuration"]
            if config["bindingKey"] != binding_key(binding):
                plans.save(
                    connection,
                    scope,
                    {
                        "enabled": False,
                        "next_run_at": None,
                        "updated_at": now,
                        "revision": plan["revision"] + 1,
                    },
                )
                return
            if any(row["plan_id"] == plan["id"] for row in runs.active(connection, scope, ACTIVE)):
                return
            today = now.replace(tzinfo=UTC).astimezone(SHANGHAI).date()
            snapshot = {k: v for k, v in config.items() if k not in ("times", "lookbackDays", "bindingKey")}
            snapshot.update(
                startDate=(today - timedelta(days=config["lookbackDays"] - 1)).isoformat(),
                endDate=today.isoformat(),
            )
            request = str(
                uuid5(NAMESPACE_URL, f"lemon:{scope}:{plan['id']}:{plan['revision']}:{plan['next_run_at']}")
            )
            self.batches.enqueue(
                connection, scope, owner, request, snapshot, binding, plan_id=plan["id"], now=now
            )
            # 停机期间错过的触发合并为一次当前窗口扫描，避免重启后追赶大量历史时刻。
            plans.save(connection, scope, {"next_run_at": next_time(config["times"], now), "updated_at": now})
