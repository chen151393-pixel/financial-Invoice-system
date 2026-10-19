"""账号绑定内的账套授权与选择，外部查询不占数据库事务。"""

from backend.core.errors import ApiError
from backend.modules.invoice.public import lemon_business_type_options, lemon_import_defaults

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
            active = runs.running(connection, scope, manual_only=True)
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
            "businessTypeOptions": lemon_business_type_options(latest["result"] if latest else None),
            "defaultBusinessTypes": lemon_import_defaults(),
        }

    def query(self, owner):
        with self.engine.connect() as connection:
            _, row = self.context(connection, owner)
        accounts = self.authorized_accounts(self.client.user_token(row["mobile"]))
        return {"items": [{"asid": account["asid"], "name": account["name"]} for account in accounts]}

    def authorized_accounts(self, token):
        professional = self.client.professional_accounts(token)
        # 空专业版列表仍是专业版结果；None 仅表示上游明确确认没有专业版服务。
        return self.client.accounts(token) if professional is None else professional

    def select(self, owner, asid):
        with self.engine.connect() as connection:
            scope, initial = self.context(connection, owner)
        accounts = self.authorized_accounts(self.client.user_token(initial["mobile"]))
        chosen = next((row for row in accounts if row["asid"] == asid), None)
        if chosen is None:
            raise ApiError(403, "当前绑定账号无权访问该账套，请刷新账套列表")
        with self.engine.begin() as connection:
            _, current = self.context(connection, owner, lock=True)
            if initial["mobile"] != current["mobile"] or runs.running(connection, scope, manual_only=True):
                raise ApiError(409, "绑定已变化或存在待核实同步，不能切换账套")
            bindings.select_account(connection, scope, asid, chosen["name"])
        return self.configuration(owner)
