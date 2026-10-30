"""发票工作台只读汇总；跨模块读取使用门面，同一数据库快照内完成。"""

import csv
import io
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_invoices, read_receipt_dates
from backend.modules.review.public import workbench_reviews
from backend.modules.source.public import (
    admission_issues,
    china_day_range,
    purchase_lines,
    workbench_declarations,
    workbench_purchases,
)
from backend.modules.task.public import unbound_notify_suppliers, workbench_tasks

from ..dao import allocation_dao, workbench_allocation_dao
from ..mapper.workbench_mapper import matching_todo, review_todo, task_todo
from ..policy.anomaly_policy import check_categories
from ..policy.comparison_policy import HIGH, MEDIUM
from ..policy.workbench_flow import declaration_positions, funnel, node_distribution
from ..policy.workbench_kpis import kpis
from ..policy.workbench_reports import BUSINESS_ZONE, month_keys, monthly_receipts, percent, supplier_ranking
from ..policy.workbench_scope import Scope, supplier_options
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


def matching_rows(connection, rows, now, supplier_id=None):
    contexts = purchase_lines(connection, [row["purchase_line_id"] for row in rows])
    if supplier_id:
        rows = [
            row for row in rows if contexts.get(row["purchase_line_id"], {}).get("supplier_id") == supplier_id
        ]
    invoices = {row["id"]: row for row in read_invoices(connection, [row["invoice_id"] for row in rows])}
    grouped = defaultdict(list)
    for row in rows:
        account = contexts.get(row["purchase_line_id"], {}).get("ns_account") or ""
        grouped[(row["invoice_id"], account)].append(row)
    return [matching_todo(key, own, invoices.get(key[0], {}), contexts, now) for key, own in grouped.items()]


def anomaly_counts(rows):
    """待审核建议按不一致的比对项分类计数（一条建议可属多类），按数量倒序。"""
    found = Counter()
    for row in rows:
        if row["status"] == "proposed":
            found.update(
                check_categories(
                    (c.get("key"), c.get("label"), c.get("result"), c.get("invoiceValue"))
                    for c in (row["checks"] or {}).get("items", [])
                )
            )
    ranked = found.most_common()
    top = Decimal(ranked[0][1]) if ranked else Decimal(0)
    return [
        {"label": label, "count": count, "percent": percent(Decimal(count), top)} for label, count in ranked
    ]


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
        scope = Scope(
            query, china_day_range(query.createdFrom, query.createdTo) if query.createdFrom else None
        )
        reviews = workbench_reviews(connection, declarations)
        positions, no_task = declaration_positions(
            declarations,
            {row["id"] for row in reviews},
            tasks,
            scope,
            lambda row: not admission_issues(row["declaration_no"], row["order_count"]),
        )
        allocations = workbench_allocation_dao.read(connection)
        scoped_reviews = [row for row in reviews if scope.declaration(row)]
        rows = [review_todo(row, now) for row in scoped_reviews]
        rows += matching_rows(connection, allocations, now, scope.supplier_id)
        rows += [
            task_todo(row, heads)
            for row in tasks
            if row["status"] != "completed" and scope.task(row, heads.get(row["customs_declaration_id"]))
        ]
        accounts = sorted(
            {row["ns_account"] for row in declarations + tasks} | {r.account for r in rows if r.account}
        )
        scoped = [r for r in rows if not query.account or r.account == query.account]
        selected, filtered_counts = select_rows(scoped, query)
        if export:
            return export_csv(selected)
        scoped_tasks = [row for row in tasks if not query.account or row["ns_account"] == query.account]
        today = now.astimezone(BUSINESS_ZONE).date()
        # 票面收票覆盖全部已入库正常人民币发票；与 NS 任务账套、审核进度无关。
        start = date.fromisoformat(f"{month_keys(today)[0]}-01")
        end = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
        receipts = read_receipt_dates(connection, start, end - timedelta(days=1))
        purchases = [
            row
            for row in workbench_purchases(connection)
            if not query.account or row["ns_account"] == query.account
        ]
        monthly = monthly_receipts(purchases, receipts, today)
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
            noTaskCount=no_task,
            supplierOptions=supplier_options(declarations, query.account),
            items=selected[start : start + query.pageSize],
            total=total,
            page=page,
            pages=pages,
            pageSize=query.pageSize,
            kpis=kpis(monthly=monthly, tasks=scoped_tasks, reviews=scoped_reviews, today=today),
            suppliers=rank,
            unknownSupplierAmounts=unknown,
            funnel=funnel(positions),
            nodes=node_distribution(scoped_tasks),
            monthly=monthly,
            unknownExpectedDates=len(
                {
                    (row["ns_account"], row["purchase_order_id"])
                    for row in purchases
                    if row["currency"] == "CNY" and not row["declaration_created_at"]
                }
            ),
            queue={
                **allocation_dao.proposal_counts(connection, HIGH, MEDIUM),
                "anomalies": anomaly_counts(allocations),
            },
            # 与“待通知供应商”指标同一任务范围（按账套筛选）
            unboundNotify=unbound_notify_suppliers(connection, scoped_tasks),
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
            "业务状态",
            "关注原因",
            "等待天数",
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
            row.stageLabel,
            row.reason,
            "" if row.waitingDays is None else str(row.waitingDays),
        ]
        # CSV 单元格按文本打开，避免外部单号、供应商名被表格程序当公式执行。
        writer.writerow(
            ["'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value for value in values]
        )
    return {"filename": "invoice-workbench.csv", "content": "\ufeff" + output.getvalue(), "count": len(rows)}
