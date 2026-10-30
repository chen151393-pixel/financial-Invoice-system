"""NS 定时计划的读取、保存与到期入队；以计划行锁保证同一触发时点只生成一次批次。"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.exc import IntegrityError

from backend.core.errors import ApiError

from ..dao import ns_plan_dao as plans
from ..dao import sync_run_dao as runs
from ..policy.ns_plan_policy import ACTIVE, KIND_HINTS, KINDS, PAUSED_ADMIN
from ..policy.schedule_policy import local_today, next_time
from ..vo.ns_plan_vo import plan_view

logger = logging.getLogger(__name__)


class NsPlanService:
    def __init__(self, batches):
        self.batches, self.engine = batches, batches.engine
        self.pulls, self.require_admin = batches.pulls, batches.require_admin

    def _blocker(self, kinds):
        """返回第一个不能执行的原因；配置齐全时返回 None。只检查配置，不调用 NS。"""
        if not self.pulls.settings.account:
            return "NS 账户未配置，不能启用定时同步"
        for kind in kinds:
            try:
                self.pulls.ensure_storage(kind)
            except ApiError as error:
                return f"{KINDS[kind][1]}：{error.message}"
        return None

    def configuration(self, owner):
        self.require_admin(owner)
        with self.engine.connect() as connection:
            plan = plan_view(plans.get(connection, self.batches.scope()))
        reason = self._blocker(list(KINDS))
        return {
            "plan": plan,
            "submit": {"allowed": reason is None, "reason": reason or "可保存并启用 NS 定时同步计划"},
            "pause": {"allowed": plan["enabled"], "reason": "暂停计划不影响已提交批次"},
            "kindOptions": [
                {"value": kind, "label": label, "hint": KIND_HINTS[kind]}
                for kind, (_, label) in KINDS.items()
            ],
            "coverage": (
                "按 NS 创建日期回扫最近若干天，只读取 NS、不写入 NS；本地已有单据按 NS 身份更新并补齐字段，"
                "没有的新增。这不是修改时间增量同步，更早创建的单据变化请在“手动补拉”页按日期拉取。"
            ),
            "timezone": "Asia/Shanghai",
        }

    def save(self, owner, body):
        self.require_admin(owner)
        if body.enabled:
            reason = self._blocker(body.kinds)
            if reason:
                raise ApiError(409, reason)
        now = datetime.now(UTC).replace(tzinfo=None)
        scope = self.batches.scope()
        values = {
            "owner": owner,
            "enabled": body.enabled,
            "revision": body.revision + 1,
            # 重新保存即表示管理员已处理自动暂停的原因，原因随之清除。
            "configuration": body.model_dump(include={"kinds", "times", "lookbackDays"}),
            "next_run_at": next_time(body.times, now) if body.enabled else None,
            "updated_at": now,
        }
        try:
            with self.engine.begin() as connection:
                previous = plans.get(connection, scope, lock=True)
                if body.revision != (previous["revision"] if previous else 0):
                    raise ApiError(409, "计划已被修改，请刷新后重新编辑")
                if previous:
                    plans.change(connection, scope, values)
                else:
                    plans.create(connection, scope, values)
        except IntegrityError:
            raise ApiError(409, "计划已被修改，请刷新后重新编辑") from None
        return self.configuration(owner)

    def tick(self, now=None):
        now = now or datetime.now(UTC).replace(tzinfo=None)
        if not self.pulls.settings.account:
            return
        scope = self.batches.scope()
        with self.engine.connect() as connection:
            # 预检查与写事务分开，避免 MySQL 可重复读持有锁前的旧快照。
            plan = plans.due(connection, scope, now)
        if not plan:
            return
        try:
            # 后台沿用计划保存人的身份，入队前复核其仍是系统管理员。
            self.require_admin(plan["owner"])
        except ApiError:
            self.pause(scope, PAUSED_ADMIN, now)
            logger.warning("ns_schedule_paused reason=owner_not_admin")
            return
        with self.engine.begin() as connection:
            plan = plans.due(connection, scope, now, lock=True)
            if not plan:
                return
            # 已有活动批次时不叠加；结束后到期计划会合并为一次最新窗口回扫。
            if runs.active(connection, scope, ACTIVE):
                return
            config = plan["configuration"]
            today = local_today(now)
            window = {
                "startDate": (today - timedelta(days=config["lookbackDays"] - 1)).isoformat(),
                "endDate": today.isoformat(),
            }
            for kind in config["kinds"]:
                request = uuid5(
                    NAMESPACE_URL, f"ns:{scope}:{plan['id']}:{plan['revision']}:{plan['next_run_at']}:{kind}"
                )
                runs.create(
                    connection,
                    {
                        "source": KINDS[kind][0],
                        "scope_key": scope,
                        "request_id": str(request),
                        "ns_plan_id": plan["id"],
                        "trigger_type": "schedule",
                        "phase": "queued",
                        "configuration": {"kind": kind, **window, "planRevision": plan["revision"]},
                        "started_by": plan["owner"],
                        "started_at": now,
                        "message": "已按计划加入后台队列，等待执行",
                    },
                )
            # 停机期间错过的触发合并为一次当前窗口回扫，避免重启后追赶大量历史时刻。
            plans.change(
                connection, scope, {"next_run_at": next_time(config["times"], now), "updated_at": now}
            )

    def pause(self, scope, reason, now):
        """自动暂停：保留配置并记录原因，管理员重新保存后恢复。"""
        with self.engine.begin() as connection:
            plan = plans.get(connection, scope, lock=True)
            if not plan or not plan["enabled"]:
                return
            plans.change(
                connection,
                scope,
                {
                    "enabled": False,
                    "next_run_at": None,
                    "revision": plan["revision"] + 1,
                    "configuration": {**plan["configuration"], "pausedReason": reason},
                    "updated_at": now,
                },
            )
