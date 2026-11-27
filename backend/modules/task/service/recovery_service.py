"""应收看板：按财务审核通过月份审计开票任务的发票回收，只读，不改变任务与节点。

任务金额、当前节点与供应商、子采购单号沿用工作台读取（workbench_tasks），与开票跟进任务台一致；
开票月份取任务对应财务审核版本的通过日期，采购员取当前负责人。口径见 recovery_policy。
"""

import csv
import io
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.search_terms import search_terms
from backend.modules.review.public import review_approval_times
from backend.modules.source.public import supplier_owner_directory

from ..dao import supplier_owner_dao
from ..policy import recovery_policy as policy
from ..vo.recovery_vo import RecoveryBoard, RecoveryExport
from .supplier_owner_reader import china_today
from .workbench_reader import workbench_tasks

READ_ERROR = "应收看板读取失败，请稍后重试"


def current_owners(records, today):
    """{(供应商, 采购抬头): 今天已生效的最新负责人}；记录已按生效日期、ID 升序。"""
    owners = {}
    for row in records:
        if row["effective_date"] <= today:
            owners[(row["supplier_id"], row["company_id"])] = row
    return owners


EXPORT_LIMIT = 100000
HEADER = (
    "开票月份",
    "供应商",
    "采购抬头",
    "采购员",
    "CD 号",
    "子采购单号",
    "应开金额",
    "已收金额",
    "未收回金额",
    "财务审核通过日期",
    "回收期限",
    "是否收回",
    "当前节点",
)


def text_cell(value):
    # CSV 单元格按文本打开，避免外部单号、供应商名被表格程序当公式执行。
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_csv(board):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(HEADER)
    count = 0
    for group in board.list.items:
        for task in group.items:
            count += 1
            writer.writerow(
                [
                    text_cell(value)
                    for value in (
                        task.approvedOn[:7],
                        group.supplierName,
                        group.companyName,
                        group.memberName,
                        task.recordNo,
                        "、".join(task.orders),
                        task.expected or "",
                        task.received or "",
                        task.outstanding or "",
                        task.approvedOn,
                        task.dueDate,
                        "是" if task.collected else "否",
                        task.nodeLabel,
                    )
                ]
            )
    month = "全部月份" if board.month == "all" else board.month
    return RecoveryExport(
        filename=f"invoice-recovery-{month}-{board.list.view}.csv",
        content="\ufeff" + output.getvalue(),
        count=count,
    )


def china_date(instant):
    moment = instant if instant.tzinfo else instant.replace(tzinfo=UTC)
    return (moment.astimezone(UTC) + timedelta(hours=8)).date()


class RecoveryService:
    def __init__(self, engine):
        self.engine = engine

    def rows(self, connection, now, today):
        tasks = workbench_tasks(connection, now)
        approved = review_approval_times(connection, list({task["review_id"] for task in tasks}))
        owners = current_owners(supplier_owner_dao.records(connection), today)
        companies = {row["id"]: row["name"] for row in supplier_owner_directory(connection)["companies"]}
        result = []
        for task in tasks:
            approved_at = approved.get(task["review_id"])
            if approved_at is None:
                raise ApiError(503, "开票任务缺少财务审核通过记录，请核实审核数据")
            approved_on = china_date(approved_at)
            month = policy.month_of(approved_on)
            owner = owners.get((task["supplier_id"], task["company_id"]))
            result.append(
                {
                    **task,
                    "company": companies.get(task["company_id"], "抬头待确认"),
                    "member_key": str(owner["member_id"]) if owner else policy.UNASSIGNED,
                    "member_name": owner["member_name"] if owner else "",
                    "approved_on": approved_on,
                    "month": month,
                    "due": policy.due_date(month),
                    "collected": policy.collected(task["status"]),
                }
            )
        return result

    def browse(self, query, now=None):
        now = now or datetime.now(UTC)
        today = china_today(now)
        try:
            with self.engine.connect() as connection:
                every = self.rows(connection, now, today)
        except SQLAlchemyError as error:
            raise ApiError(503, READ_ERROR) from error
        return self.board(every, query, today)

    def export(self, query, now=None):
        """导出当前条件下清单的全部任务（不分页），逐任务一行。"""
        board = self.browse(query.model_copy(update={"page": 1, "pageSize": EXPORT_LIMIT}), now)
        return export_csv(board)

    @staticmethod
    def board(every, query, today):
        default = policy.default_month(today)
        month = query.month or default
        terms = [term.casefold() for term in search_terms(query.supplierName)]
        orders = [term.casefold() for term in search_terms(query.orderNo)]
        scoped = [row for row in every if policy.matches(row, query, terms, orders)]
        cohort = scoped if month == "all" else [row for row in scoped if row["month"] == month]
        overdue = [row for row in scoped if policy.is_overdue(row, today)]
        months, recent = policy.months(scoped, today)
        chosen = policy.view_rows(cohort, overdue, query.view)
        groups = policy.groups(chosen, query.view, today)
        total = len(groups)
        start = (query.page - 1) * query.pageSize
        members = {}
        for row in every:
            if row["member_key"] != policy.UNASSIGNED:
                members[row["member_key"]] = row["member_name"]
        companies = {str(row["company_id"]): row["company"] for row in every if row["company_id"]}
        seen = sorted({row["month"] for row in every} | set(policy.window(today)), reverse=True)
        return RecoveryBoard(
            today=today.isoformat(),
            month=month,
            monthLabel="全部月份" if month == "all" else f"{policy.month_label(month)}开票",
            dueDate=None if month == "all" else policy.due_date(month).isoformat(),
            defaultMonth=default,
            cards=policy.cards(cohort, overdue, month, today),
            months=months,
            recentRate=recent,
            buyers=policy.buyers(cohort),
            concentration=policy.concentration(cohort),
            list={
                "view": query.view,
                "summary": policy.summary(chosen, policy.list_amount(query.view)),
                "items": groups[start : start + query.pageSize],
                "total": total,
                "page": query.page,
                "pageSize": query.pageSize,
                "pages": max(1, (total + query.pageSize - 1) // query.pageSize),
            },
            options={
                "buyers": [
                    {"id": key, "name": name}
                    for key, name in sorted(members.items(), key=lambda item: item[1])
                ]
                + [{"id": policy.UNASSIGNED, "name": "未指定采购员"}],
                "companies": [
                    {"id": key, "name": name}
                    for key, name in sorted(companies.items(), key=lambda item: item[1])
                ],
                "months": [
                    {
                        "id": value,
                        "name": policy.month_label(value)
                        if value[:4] == str(today.year)
                        else f"{value[:4]}年{policy.month_label(value)}",
                    }
                    for value in seen[:12]
                ],
            },
        )
