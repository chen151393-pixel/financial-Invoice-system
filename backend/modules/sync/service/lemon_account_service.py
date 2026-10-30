"""账号绑定内的账套授权与选择，外部查询不占数据库事务。"""

from backend.core.errors import ApiError
from backend.modules.invoice.public import lemon_business_type_options, lemon_import_defaults

from ..dao import lemon_binding_dao as bindings
from ..dao import lemon_run_dao as runs
from ..policy.lemon_binding_policy import configuration_reason
from ..policy.lemon_detail_policy import edition_view
from ..vo.lemon_invoice_vo import run_view
from .invoice_account_service import invoice_accounts


class LemonAccountService:
    def __init__(self, binding, client):
        self.binding, self.client = binding, client
        self.engine = binding.engine

    def invoice_accounts(self, owner):
        return invoice_accounts(self.binding, owner)

    def context(self, connection, owner, *, lock=False):
        self.binding._check(owner)
        scope = self.binding._scope(owner)
        row = bindings.get(connection, scope, lock=lock)
        if not row or row["status"] != "bound":
            raise ApiError(409, "请先完成已有账号绑定并核实状态")
        return scope, row

    def configuration(self, owner):
        self.binding.require_admin(owner)
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
        return {
            "items": [
                {"asid": account["asid"], "name": account["name"], **edition_view(account)}
                for account in accounts
            ]
        }

    def authorized_accounts(self, token):
        # 同一账号可同时拥有专业版和免费版账套，两边都查；任一边失败整体报错，不以半个列表冒充完整。
        # None 表示上游明确确认没有专业版服务，按空列表处理。
        professional = self.client.professional_accounts(token) or []
        free = [{**account, "edition": "free"} for account in self.client.accounts(token)]
        # 拉票按 asid 判断版本；两版编号区间实测不重叠（2026-10-29），万一重号则无法区分，明确拒绝。
        if {row["asid"] for row in professional} & {row["asid"] for row in free}:
            raise ApiError(502, "柠檬云专业版与免费版返回了相同的账套编号，无法区分版本，本次未继续")
        return professional + free

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
