"""账号绑定内的账套授权与选择，外部查询不占数据库事务。"""

from backend.core.errors import ApiError

from ..dao import lemon_binding_dao as bindings
from ..dao import lemon_run_dao as runs
from ..policy.lemon_binding_policy import configuration_reason
from ..vo.lemon_invoice_vo import run_view


class LemonAccountService:
    def __init__(self, binding, client):
        self.binding, self.client = binding, client
        self.engine = binding.engine

    def context(self, connection, owner, *, lock=False):
        self.binding._check(owner)
        scope = self.binding._scope(owner)
        row = bindings.get(connection, scope, lock=lock)
        if not row or row["status"] != "bound":
            raise ApiError(409, "请先完成已有账号绑定并核实状态")
        return scope, row

    def configuration(self, owner):
        if owner != f"user:{self.binding.settings.admin_user}":
            raise ApiError(403, "只有本系统管理员可同步柠檬云发票")
        scope = self.binding._scope(owner)
        with self.engine.connect() as connection:
            row = bindings.get(connection, scope)
            latest = runs.latest(connection, scope)
            active = runs.running(connection, scope)
        reason = configuration_reason(self.binding.settings)
        if not row or row["status"] != "bound":
            reason = reason or "请先完成已有账号绑定并核实状态"
        selected = (
            {"asid": row["selected_asid"], "name": row["selected_name"]}
            if row and row["selected_asid"]
            else None
        )
        query_reason = reason or (
            "存在执行中或结果待核实的同步，请查询原结果" if active else "可查询已授权账套"
        )
        sync_reason = reason or (
            "存在执行中或结果待核实的同步，请查询原结果"
            if active
            else "请先查询并选择账套"
            if not selected
            else "可按开票日期拉取并保存进项票"
        )
        return {
            "query": {"allowed": not reason and not active, "reason": query_reason},
            "sync": {"allowed": not reason and not active and bool(selected), "reason": sync_reason},
            "selected": selected,
            "latest": run_view(latest),
        }

    def query(self, owner):
        with self.engine.connect() as connection:
            _, row = self.context(connection, owner)
        return {"items": self.authorized_accounts(self.client.user_token(row["mobile"]))}

    def authorized_accounts(self, token):
        defaults = self.client.accounts(token)
        # 使用上游真实返回的账套提供权限查询上下文，不把它自动选为业务账套。
        services = self.client.account_service_ids(token, defaults[0]["asid"] if defaults else None)
        if not services:
            return defaults
        if len(services) > 50:
            raise ApiError(502, "柠檬云专业版服务数量超出单次查询范围，请联系管理员")
        # 已发现专业版服务时，只展示这些服务下的账套，不回退成免费版查询成功。
        accounts = {}
        for service_id in services:
            for row in self.client.accounts(token, service_id):
                previous = accounts.get(row["asid"])
                if previous and previous != row:
                    raise ApiError(502, "柠檬云不同服务返回的同一账套信息不一致，请核实")
                accounts[row["asid"]] = row
            if len(accounts) > 1000:
                raise ApiError(502, "柠檬云账套数量超出单次查询范围，请联系管理员")
        return list(accounts.values())

    def select(self, owner, asid):
        with self.engine.connect() as connection:
            scope, initial = self.context(connection, owner)
        accounts = self.authorized_accounts(self.client.user_token(initial["mobile"]))
        chosen = next((row for row in accounts if row["asid"] == asid), None)
        if chosen is None:
            raise ApiError(403, "当前绑定账号无权访问该账套，请刷新账套列表")
        with self.engine.begin() as connection:
            _, current = self.context(connection, owner, lock=True)
            if initial["mobile"] != current["mobile"] or runs.running(connection, scope):
                raise ApiError(409, "绑定已变化或存在待核实同步，不能切换账套")
            bindings.select_account(connection, scope, asid, chosen["name"])
        return self.configuration(owner)
