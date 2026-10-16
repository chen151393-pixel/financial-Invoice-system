"""手动拉票用例：持久请求、事务外读取、事件原子保存。"""

import hashlib
from datetime import date

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import lemon_run_dao as runs
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

    def _start(self, owner, body):
        with self.engine.begin() as connection:
            scope, binding = self.accounts.context(connection, owner, lock=True)
            previous = runs.get(connection, scope, body.requestId)
            if previous:
                if (previous["asid"], str(previous["start_date"]), str(previous["end_date"])) != (
                    body.asid,
                    body.startDate,
                    body.endDate,
                ):
                    raise ApiError(409, "同一请求编号不能用于不同账套或日期范围")
                return scope, binding, previous
            if runs.running(connection, scope):
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
                },
            )
        return scope, binding, None

    def pull(self, owner, body):
        try:
            scope, binding, previous = self._start(owner, body)
            if previous:
                return run_view(previous)
            self._execute(owner, body, scope, binding)
            return self.read(owner, body.requestId)
        except SQLAlchemyError:
            # 提交响应丢失时可能已成功；不清除 running，不自动重拉。
            raise ApiError(503, "同步数据库结果待核实，请刷新查询原请求；不要重新发起拉取") from None

    def _execute(self, owner, body, scope, binding):
        try:
            token = self.client.user_token(binding["mobile"])
            accounts = self.client.accounts(token)
            if not any(row["asid"] == body.asid for row in accounts):
                raise ApiError(403, "当前账号已无该账套访问权限，本次未保存")
            records = self.client.invoices(token, body.asid, body.startDate, body.endDate)
            namespace = hashlib.sha256(
                f"{self.accounts.binding.settings.lemon_host}|{body.asid}".encode()
            ).hexdigest()
            with transaction(self.engine) as connection:
                _, current = self.accounts.context(connection, owner, lock=True)
                if current["mobile"] != binding["mobile"] or current["selected_asid"] != body.asid:
                    raise ApiError(409, "拉取期间绑定或账套已变化，本次未保存")
                self.events.publish(
                    connection,
                    LemonInvoicesFetched(
                        scope,
                        body.requestId,
                        "open2:" + namespace,
                        date.fromisoformat(body.startDate),
                        date.fromisoformat(body.endDate),
                        tuple(records),
                    ),
                )
                if runs.get(connection, scope, body.requestId)["status"] != "completed":
                    raise ApiError(503, "发票保存订阅未完成，本次事务已回滚")
        except ApiError as error:
            with self.engine.begin() as connection:
                runs.finish(connection, scope, body.requestId, "failed", error=error.message[:500])
            raise


def on_lemon_invoices_stored(connection, event):
    if runs.finish(connection, event.scope, event.request_id, "completed", result=event.result) != 1:
        raise ApiError(409, "同步记录状态已变化，发票保存已回滚")
