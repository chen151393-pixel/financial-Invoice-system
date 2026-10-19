"""列表补拉用例：由本地来源生成范围，复用持久同步记录与原子保存。"""

from pydantic import ValidationError

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_lemon_refresh_targets

from ..dao import lemon_run_dao as runs
from ..dto.lemon_invoice_dto import PullLemonInvoices
from ..policy.lemon_detail_policy import account_namespace, refresh_action
from ..vo.lemon_invoice_vo import run_view


class LemonDetailRefreshService:
    def __init__(self, service):
        self.service, self.accounts = service, service.accounts

    def actions(self, owner, body):
        config = self.accounts.configuration(owner)
        with self.service.engine.connect() as connection:
            rows = read_lemon_refresh_targets(connection, [int(value) for value in body.invoiceIds])
        by_id = {str(row["id"]): row for row in rows}
        account = self._account(config["selected"]["asid"]) if config["selected"] else None
        return {
            "rows": [
                {
                    "invoiceId": identifier,
                    **(
                        refresh_action(by_id.get(identifier), account)
                        if config["sync"]["allowed"]
                        else config["sync"]
                    ),
                }
                for identifier in body.invoiceIds
            ],
            "latest": config["latest"],
        }

    def refresh(self, owner, body):
        with self.service.engine.connect() as connection:
            scope, binding = self.accounts.context(connection, owner)
            previous = runs.get(connection, scope, body.requestId)
            if previous:
                if (previous["result"] or {}).get("invoiceIds") != body.invoiceIds:
                    raise ApiError(409, "同一请求编号不能用于不同补拉范围")
                return run_view(previous)
            rows = read_lemon_refresh_targets(connection, [int(value) for value in body.invoiceIds])
        if len(rows) != len(body.invoiceIds):
            raise ApiError(404, "部分所选发票不存在，请刷新列表")
        account = self._account(binding["selected_asid"])
        for row in rows:
            action = refresh_action(row, account)
            if not action["allowed"]:
                raise ApiError(409, action["reason"])
        try:
            request = PullLemonInvoices(
                requestId=body.requestId,
                asid=binding["selected_asid"],
                startDate=min(row["invoice_date"] for row in rows).isoformat(),
                endDate=max(row["invoice_date"] for row in rows).isoformat(),
                businessTypes=sorted({row["business_type"] for row in rows}),
            )
        except ValidationError:
            raise ApiError(422, "所选发票日期跨度超过 366 天或来源信息不完整，请分批补拉") from None
        return self.service.pull(owner, request, targets=rows)

    def _account(self, asid):
        return account_namespace(self.accounts.binding.settings.lemon_host, asid)
