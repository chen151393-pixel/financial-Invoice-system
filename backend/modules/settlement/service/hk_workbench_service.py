"""香港中转工作区：只读组合候选报关单、批次与资料状态，不改变回款业务规则。"""

import csv
import io
import math

from backend.core.errors import ApiError
from backend.core.names import normalize_name

from ..dao import batch_dao, batch_item_dao
from ..mapper.batch_mapper import detail
from ..policy import hk_workbench_policy as rules
from ..policy.amount_policy import balance_check, money
from ..policy.batch_state_policy import status_label
from ..vo.hk_workbench_vo import HkExport, HkReceiptCheck, HkWorkbench
from .batch_service import validate_selection
from .receivable_service import china_today


class HkWorkbenchService:
    def __init__(self, engine, candidates, reader, *, fee_alert, today=china_today):
        self.engine, self.candidates, self.reader = engine, candidates, reader
        self.fee_alert, self.today = fee_alert, today

    def query(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        today = self.today()
        with self.engine.connect() as connection:
            pending, heads, items = self._selection(connection, body, today)
            stages = rules.stages(pending, heads)
            shown = [
                row
                for row in heads
                if body.stage == "all"
                or (row["status"] in rules.OPEN if body.stage == "open" else row["status"] == body.stage)
            ]
            page_count = max(1, math.ceil(len(shown) / body.pageSize))
            page = min(body.page, page_count)
            result = []
            for row in shown[(page - 1) * body.pageSize : page * body.pageSize]:
                children = items.get(row["id"], [])
                state = self.reader.state(connection, row, children)
                issue = state["issues"][0] if state["issues"] else ""
                result.append(
                    dict(
                        batch=detail(row, children, self.fee_alert, issue),
                        packageUrl=f"/api/settlement/batches/{row['id']}/package",
                        package=dict(
                            allowed=not state["issues"] and row["status"] != "cancelled",
                            reason=issue or ("批次已作废" if row["status"] == "cancelled" else ""),
                        ),
                        **rules.batch_state(row, children, state, today),
                    )
                )
        pending_pages = max(1, math.ceil(len(pending) / body.pendingPageSize))
        pending_page = min(body.pendingPage, pending_pages)
        return HkWorkbench(
            stages=stages,
            pending=[
                rules.pending(row, today)
                for row in pending[
                    (pending_page - 1) * body.pendingPageSize : pending_page * body.pendingPageSize
                ]
            ],
            pendingTotal=len(pending),
            pendingPage=pending_page,
            pendingPageCount=pending_pages,
            batches=result,
            batchTotal=len(shown),
            page=page,
            pageCount=page_count,
            asOf=str(today),
        )

    def _selection(self, connection, body, today):
        declarations = self.candidates.load(connection, consignee=body.consignee, limit=None)
        pending = [
            row
            for row in declarations
            if row["route"] == "hk_transit"
            and not row["batch_no"]
            and rules.matches(row, body.keyword, ("declaration_no", "record_no", "consignee"))
        ]
        pending.sort(
            key=lambda row: (
                row["export_date"] is None,
                row["export_date"] or today,
                row["declaration_no"],
            )
        )
        _, heads = batch_dao.page(connection, {"route": "hk_transit"}, 0, None)
        items = batch_item_dao.of_batches(connection, [row["id"] for row in heads])
        wanted = normalize_name(body.consignee)
        heads = [
            row
            for row in heads
            if (not wanted or wanted in normalize_name(row["consignee"]))
            and (
                rules.matches(
                    row,
                    body.keyword,
                    ("batch_no", "received_reference", "remitted_reference", "consignee"),
                )
                or any(
                    rules.matches(item, body.keyword, ("declaration_no", "record_no", "sales_orders"))
                    for item in items.get(row["id"], [])
                )
            )
        ]
        return pending, heads, items

    def preview(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            rows = self.candidates.load(connection, numbers=body.declarationNos)
        _, _, currency, total = validate_selection(rows, body.declarationNos)
        check = balance_check(total, body.receivedAmount, body.receivedFee, self.fee_alert)
        reason = "请填写正数到账金额" if body.receivedAmount <= 0 else ""
        return HkReceiptCheck(
            currency=currency,
            declaredTotal=str(money(total)),
            arrivedTotal=str(money(body.receivedAmount + body.receivedFee)),
            difference=str(check["difference"]),
            balanced=check["balanced"],
            warnings=check["warnings"],
            submit=dict(allowed=not reason, reason=reason),
        )

    def export(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        today = self.today()
        with self.engine.connect() as connection:
            pending, heads, _ = self._selection(connection, body, today)
        records = []
        if body.stage in ("open", "register", "all"):
            records.extend(
                [
                    "报关单",
                    row["declaration_no"],
                    row["consignee"],
                    row["currency"],
                    str(money(row["amount"])) if row["amount"] is not None else "",
                    str(row["export_date"] or ""),
                    "待登记回款",
                    "",
                ]
                for row in pending
            )
        for row in heads:
            if body.stage != "all" and not (
                row["status"] in rules.OPEN if body.stage == "open" else row["status"] == body.stage
            ):
                continue
            records.append(
                [
                    "批次",
                    row["batch_no"],
                    row["consignee"],
                    row["currency"],
                    str(money(row["declared_total"])),
                    str(row["received_on"]),
                    status_label("hk_transit", row["status"]),
                    row["received_reference"] or "",
                ]
            )
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(
            ["类型", "编号", "境外收货人", "币种", "报关金额", "出口或到账日期", "状态", "流水号"]
        )
        for record in records:
            # Excel 打开 CSV 时不执行来自导入文本的公式。
            writer.writerow(
                [
                    "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
                    for value in record
                ]
            )
        return HkExport(fileName=f"香港中转-{today}.csv", content="\ufeff" + stream.getvalue())
