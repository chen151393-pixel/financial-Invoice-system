"""拉票用例（手动及后台分片共用）：持久请求、事务外读取、事件原子保存。"""

from datetime import date

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.invoice.public import lemon_detail_ids, read_lemon_refresh_targets

from ..dao import lemon_run_dao as runs
from ..policy.lemon_detail_policy import account_namespace, selected_records
from ..policy.lemon_invoice_policy import run_business_types
from ..public import LemonInvoicesFetched
from ..vo.lemon_invoice_vo import run_view


class LemonInvoiceService:
    def __init__(self, accounts, events):
        self.accounts, self.events = accounts, events
        self.engine, self.client = accounts.engine, accounts.client

    def read(self, owner, request_id):
        with self.engine.connect() as connection:
            scope, _ = self.accounts.context(connection, owner)
            row = runs.get(connection, scope, request_id)
        if not row:
            raise ApiError(404, "未找到当前账号的同步记录，请刷新同步状态")
        return run_view(row)

    def _start(self, owner, body, targets=None):
        invoice_ids = sorted((str(row["id"]) for row in targets or []), key=int)
        with self.engine.begin() as connection:
            scope, binding = self.accounts.context(connection, owner, lock=True)
            previous = runs.get(connection, scope, body.requestId)
            if previous:
                if (previous["result"] or {}).get("invoiceIds", []) != invoice_ids:
                    raise ApiError(409, "同一请求编号不能用于不同补拉范围")
                if set(run_business_types(previous)) != set(body.businessTypes):
                    raise ApiError(409, "同一请求编号不能用于不同业务类型，请查询原结果")
                if (previous["asid"], str(previous["start_date"]), str(previous["end_date"])) != (
                    body.asid,
                    body.startDate,
                    body.endDate,
                ):
                    raise ApiError(409, "同一请求编号不能用于不同账套或日期范围")
                return scope, binding, previous
            if runs.running(connection, scope, asid=body.asid):
                raise ApiError(409, "已有执行中或结果待核实的同步，请先查询原结果")
            if binding["selected_asid"] != body.asid:
                raise ApiError(409, "所选账套已变化，请刷新后重新选择")
            runs.create(
                connection,
                {
                    "scope_key": scope,
                    "request_id": body.requestId,
                    "asid": body.asid,
                    "account_name": binding["selected_name"],
                    "start_date": date.fromisoformat(body.startDate),
                    "end_date": date.fromisoformat(body.endDate),
                    "status": "running",
                    # JSON 中保留本次请求筛选快照；失败和进程重启也不能丢失幂等依据。
                    "result": {"businessTypes": body.businessTypes, "invoiceIds": invoice_ids},
                },
            )
        return scope, binding, None

    def claim_background(self, connection, scope, body):
        """与队列领取同事务：复核同账套互斥后，把排队分片转为执行中；不读写页面当前账套。"""
        if runs.running(connection, scope, asid=body.asid):
            raise ApiError(409, "该账套已有执行中或结果待核实的拉取，本日期分片未执行")
        if runs.claim(connection, scope, body.requestId) != 1:
            raise ApiError(409, "分片已被领取或状态已变化，本次未执行")

    def pull(self, owner, body, *, targets=None):
        try:
            scope, binding, previous = self._start(owner, body, targets)
            if previous:
                return run_view(previous)
            self._execute(owner, body, scope, binding, targets)
            return self.read(owner, body.requestId)
        except SQLAlchemyError:
            # 提交响应丢失时可能已成功；不清除 running，不自动重拉。
            raise ApiError(503, "同步数据库结果待核实，请刷新查询原请求；不要重新发起拉取") from None

    def _fetch(self, body, binding, targets):
        token = self.client.user_token(binding["mobile"])
        accounts = self.accounts.authorized_accounts(token)
        chosen = next((row for row in accounts if row["asid"] == body.asid), None)
        if chosen is None:
            raise ApiError(403, "当前账号已无该账套访问权限，本次未保存")
        professional = chosen.get("edition") == "professional"
        if targets is not None and not professional:
            raise ApiError(409, "当前账套已不是专业版，不能补拉原专业版发票")
        reader = self.client.professional_invoices if professional else self.client.invoices
        records = selected_records(reader(token, body.asid, body.startDate, body.endDate), targets)
        selected_ids = (
            {row["InvoiceId"] for row in records}
            if targets is not None
            else lemon_detail_ids(records, body.businessTypes)
        )
        records = self.client.invoice_details(
            token, body.asid, records, selected_ids, professional=professional
        )
        return professional, chosen["name"], records

    def _execute(self, owner, body, scope, binding, targets=None, *, background=False):
        try:
            professional, account_name, records = self._fetch(body, binding, targets)
            namespace = account_namespace(self.accounts.binding.settings.lemon_host, body.asid, professional)
            with transaction(self.engine) as connection:
                _, current = self.accounts.context(connection, owner, lock=True)
                if current["mobile"] != binding["mobile"] or (
                    not background and current["selected_asid"] != body.asid
                ):
                    raise ApiError(409, "拉取期间绑定或账套已变化，本次未保存")
                if targets is not None:
                    current_targets = read_lemon_refresh_targets(connection, [row["id"] for row in targets])
                    if current_targets != targets:
                        raise ApiError(409, "补拉期间发票版本已变化，本次未保存，请刷新后重新补拉")
                self.events.publish(
                    connection,
                    LemonInvoicesFetched(
                        scope,
                        body.requestId,
                        namespace,
                        date.fromisoformat(body.startDate),
                        date.fromisoformat(body.endDate),
                        tuple(records),
                        tuple(body.businessTypes),
                        account_name,
                    ),
                )
                if runs.get(connection, scope, body.requestId)["status"] != "completed":
                    raise ApiError(503, "发票保存订阅未完成，本次事务已回滚")
        except ApiError as error:
            with self.engine.begin() as connection:
                runs.finish(connection, scope, body.requestId, "failed", error=error.message[:500])
            raise


def on_lemon_invoices_stored(connection, event):
    original = runs.get(connection, event.scope, event.request_id)
    result = {**(original["result"] or {}), **event.result} if original else event.result
    if runs.finish(connection, event.scope, event.request_id, "completed", result=result) != 1:
        raise ApiError(409, "同步记录状态已变化，发票保存已回滚")
