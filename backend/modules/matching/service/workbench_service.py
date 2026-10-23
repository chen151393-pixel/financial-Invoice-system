"""发票工作台只读汇总；跨模块读取使用门面，同一数据库快照内完成。"""

import csv
import io
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import invoice_daily_amounts, latest_invoice_date, read_invoices
from backend.modules.review.public import workbench_reviews
from backend.modules.source.public import purchase_lines, workbench_declarations
from backend.modules.task.public import workbench_tasks

from ..dao import workbench_allocation_dao
from ..mapper.workbench_mapper import matching_todo, review_todo, task_todo
from ..policy.workbench_reports import BUSINESS_ZONE, invoice_trend, month_report, supplier_ranking
from ..vo.workbench_vo import Workbench, WorkbenchCounts


def counts(rows):
    return WorkbenchCounts(
        all=len(rows),
        review=sum(r.kind == "review" for r in rows),
        matching=sum(r.kind == "matching" for r in rows),
        task=sum(r.kind == "task" for r in rows),
        reverify=sum(r.kind == "matching" and r.attention for r in rows),
        preparation=sum(r.kind == "task" and r.attention for r in rows),
    )


def select_rows(rows, query):
    keyword = query.keyword.strip().casefold()
    found = [
        r
        for r in rows
        if not keyword or keyword in " ".join((r.title, r.subtitle, r.party, r.account)).casefold()
    ]
    filtered_counts = counts(found)
    selected = [r for r in found if query.kind in ("all", r.kind)]
    if query.sort == "priority":
        selected.sort(key=lambda r: (r.priority, r.createdAt, r.key))
    else:
        selected.sort(key=lambda r: (r.createdAt, r.key), reverse=query.sort == "newest")
    return selected, filtered_counts


def matching_rows(connection):
    rows = workbench_allocation_dao.read(connection)
    contexts = purchase_lines(connection, [row["purchase_line_id"] for row in rows])
    invoices = {row["id"]: row for row in read_invoices(connection, [row["invoice_id"] for row in rows])}
    grouped = defaultdict(list)
    for row in rows:
        account = contexts.get(row["purchase_line_id"], {}).get("ns_account") or ""
        grouped[(row["invoice_id"], account)].append(row)
    return [matching_todo(key, own, invoices.get(key[0], {}), contexts) for key, own in grouped.items()]


class WorkbenchService:
    def __init__(self, engine):
        self.engine = engine

    def read(self, query, *, export=False):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        try:
            with self.engine.connect() as connection:
                if connection.dialect.name == "mysql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                with connection.begin():
                    return self._read(connection, query, datetime.now(UTC), export)
        except SQLAlchemyError:
            raise ApiError(503, "工作台读取失败，请检查数据库及迁移状态后重试") from None

    def _read(self, connection, query, now, export):
        declarations = workbench_declarations(connection)
        tasks = workbench_tasks(connection, now)
        heads = {row["id"]: row for row in declarations}
        rows = [review_todo(row) for row in workbench_reviews(connection, declarations)]
        rows += matching_rows(connection)
        rows += [task_todo(row, heads) for row in tasks if row["status"] != "completed"]
        accounts = sorted(
            {row["ns_account"] for row in declarations + tasks} | {r.account for r in rows if r.account}
        )
        scoped = [r for r in rows if not query.account or r.account == query.account]
        selected, filtered_counts = select_rows(scoped, query)
        if export:
            return export_csv(selected)
        scoped_tasks = [r for r in tasks if not query.account or r["ns_account"] == query.account]
        today = now.astimezone(BUSINESS_ZONE).date()
        latest = latest_invoice_date(connection)
        trend_end = query.trendEnd or today
        trend_start = query.trendStart or today.replace(day=1)
        rank, unknown = supplier_ranking(scoped_tasks)
        total = len(selected)
        pages = max(1, (total + query.pageSize - 1) // query.pageSize)
        page = min(query.page, pages)
        start = (page - 1) * query.pageSize
        return Workbench(
            generatedAt=now.isoformat(),
            accounts=accounts,
            counts=counts(scoped),
            filteredCounts=filtered_counts,
            items=selected[start : start + query.pageSize],
            total=total,
            page=page,
            pages=pages,
            pageSize=query.pageSize,
            month=month_report(scoped_tasks, today),
            suppliers=rank,
            unknownSupplierAmounts=unknown,
            trendStart=trend_start.isoformat(),
            trendEnd=trend_end.isoformat(),
            latestInvoiceDate=latest.isoformat() if latest else None,
            trend=invoice_trend(
                invoice_daily_amounts(connection, trend_start, trend_end), trend_end, trend_start
            ),
        )


def export_csv(rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "类型",
            "关联单据",
            "关联编号",
            "供应商或主体",
            "账套",
            "币种",
            "金额",
            "金额口径",
            "状态",
            "关注原因",
        ]
    )
    labels = {"review": "财务核对", "matching": "发票比对", "task": "开票跟进"}
    for row in rows:
        values = [
            labels[row.kind],
            row.title,
            row.subtitle,
            row.party,
            row.account,
            row.currency,
            row.amount or "",
            row.amountLabel,
            row.statusLabel,
            row.reason,
        ]
        # CSV 单元格按文本打开，避免外部单号、供应商名被表格程序当公式执行。
        writer.writerow(
            ["'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value for value in values]
        )
    return {"filename": "invoice-workbench.csv", "content": "\ufeff" + output.getvalue(), "count": len(rows)}
