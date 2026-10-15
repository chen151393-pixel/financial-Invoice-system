"""开票跟进查询：任务列表（按供应商或报关单分组分页）与任务详情。"""

from collections import Counter

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import document_dao, event_dao, notification_dao, supplier_group_dao, task_dao, task_line_dao
from ..mapper import notification_mapper, task_mapper
from ..policy.task_policy import SUPERSEDED_REASON, missing_identity_reasons
from ..vo.capability import Capability
from ..vo.task_vo import TaskDetail, TaskDocument, TaskGroup, TaskList

READ_ERROR = "开票任务读取失败，请检查业务数据库及迁移状态"


class TaskService:
    def __init__(self, engine, directory, contracts=None, archive=None):
        self.engine, self.directory = engine, directory
        self.contracts, self.archive = contracts, archive

    def browse(self, query):
        found = (
            self.directory.search(query.keyword) if query.keyword else {"supplier_ids": [], "order_ids": []}
        )
        where = task_dao.conditions(
            scope=query.status,
            account=query.account,
            keyword=query.keyword,
            supplier_ids=found["supplier_ids"],
            order_ids=found["order_ids"],
        )
        try:
            with self.engine.connect() as connection:
                offset = (query.page - 1) * query.pageSize
                total, keys = task_dao.group_page(connection, where, query.groupBy, offset, query.pageSize)
                rows = task_dao.in_groups(connection, where, query.groupBy, keys)
                lines = task_line_dao.by_tasks(connection, [row["id"] for row in rows])
                status_counts = task_dao.status_counts(connection, where)
                accounts = task_dao.accounts(connection)
        except SQLAlchemyError:
            raise ApiError(503, READ_ERROR) from None
        names = self._names(rows, lines)
        groups = [self._group(query.groupBy, key, rows, lines, names) for key in keys]
        return TaskList(
            groupBy=query.groupBy,
            groups=groups,
            counts=task_mapper.counts(status_counts),
            accounts=accounts,
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (total + query.pageSize - 1) // query.pageSize),
        )

    def _names(self, tasks, lines):
        return self.directory.describe(
            supplier_ids=[task["supplier_id"] for task in tasks if task["supplier_id"]],
            company_ids=[task["company_id"] for task in tasks if task["company_id"]],
            order_ids=[line["purchase_order_id"] for line in lines],
            line_ids=[line["purchase_line_id"] for line in lines],
        )

    def _group(self, group_by, key, rows, lines, names):
        column = "supplier_id" if group_by == "supplier" else "customs_declaration_id"
        selected = [row for row in rows if row[column] == key]
        summaries = [
            task_mapper.summary(row, [line for line in lines if line["task_id"] == row["id"]], names)
            for row in selected
        ]
        if group_by == "supplier":
            label = summaries[0].supplier
        else:
            label = summaries[0].recordNumber or "报关单号缺失"
        return TaskGroup(
            id="none" if key is None else str(key),
            label=label,
            account=selected[0]["ns_account"],
            counts=task_mapper.counts(Counter(row["status"] for row in selected)),
            tasks=summaries,
        )

    def _load(self, task_id):
        try:
            with self.engine.connect() as connection:
                task = task_dao.get(connection, task_id)
                if task is None:
                    raise ApiError(404, "开票任务不存在")
                return {
                    "task": task,
                    "lines": task_line_dao.by_tasks(connection, [task_id]),
                    "documents": document_dao.by_task(connection, task_id),
                    "notifications": notification_dao.history(connection, task_id),
                    "events": event_dao.by_task(connection, task_id),
                    "binding": supplier_group_dao.by_supplier(connection, task["supplier_id"])
                    if task["supplier_id"]
                    else None,
                }
        except SQLAlchemyError:
            raise ApiError(503, READ_ERROR) from None

    def order_ids(self, lines):
        return sorted({line["purchase_order_id"] for line in lines})

    def detail(self, task_id):
        data = self._load(task_id)
        task, lines = data["task"], data["lines"]
        names = self._names([task], lines)
        summary = task_mapper.summary(task, lines, names)
        documents = self._documents(task, self.order_ids(lines), data["documents"], names)
        ready = bool(documents) and all(doc.status == "ready" for doc in documents)
        binding = data["binding"] if data["binding"] and data["binding"]["enabled"] else None
        group_reason = (
            "已带出保存的供应商默认群；发送前仍需核对群及群主。"
            if binding
            else "尚未配置有效的供应商默认群，请先维护供应商群配置。"
        )
        attachments = [doc.filename for doc in documents if doc.status == "ready"]
        notification = notification_mapper.view(
            task, summary, data["notifications"], attachments, binding, group_reason
        )
        superseded = task["status"] == "superseded"
        prepare_reason = next((doc.prepare.reason for doc in documents if not doc.prepare.allowed), "")
        return TaskDetail(
            task=summary,
            lines=task_mapper.lines(lines, names, task["currency"]),
            reasons=missing_identity_reasons(task["supplier_id"], task["company_id"], task["currency"]),
            sourceStatus="superseded" if superseded else "current",
            sourceMessage=SUPERSEDED_REASON
            if superseded
            else "任务按财务审核通过时冻结的应开数量和金额跟进。",
            prepare=Capability(
                allowed=any(doc.prepare.allowed for doc in documents),
                reason="子采购合同已保存到共享盘"
                if ready
                else prepare_reason or "获取子采购合同并保存到共享盘",
            ),
            notify=notification.send,
            compare=Capability(
                allowed=not superseded,
                reason="在发票比对页审核比对建议；通过或取消后自动更新任务行已收与任务状态。",
            ),
            steps=task_mapper.steps(
                task["status"],
                ready,
                bool(data["notifications"] and data["notifications"][0]["status"] == "sent"),
                notification.statusLabel,
            ),
            documents=documents,
            downloadEnvironment=self.contracts.environment if self.contracts else "",
            notification=notification,
            events=task_mapper.events(data["events"]),
        )

    def _documents(self, task, order_ids, rows, names):
        saved = {row["purchase_order_id"]: row for row in rows}
        unavailable = (
            SUPERSEDED_REASON
            if task["status"] == "superseded"
            else "合同共享盘路径尚未配置"
            if self.archive is None or self.archive.root is None
            else "子采购合同下载接口尚未配置"
            if self.contracts is None
            else self.contracts.unavailable_reason()
        )
        result = []
        for order_id in order_ids:
            row = saved.get(order_id)
            number = names["orders"].get(order_id) or ""
            archived = bool(row and row["status"] == "archived")
            block = unavailable or ("子采购单编号缺失" if not number else "")
            result.append(
                TaskDocument(
                    orderId=str(order_id),
                    orderNumber=number,
                    status="ready"
                    if archived
                    else "failed"
                    if row and row["status"] == "failed"
                    else "pending",
                    environment=row["ns_environment"]
                    if row
                    else (self.contracts.environment if self.contracts else ""),
                    nsId=(row["ns_file_id"] or "") if row else "",
                    filename=(row["filename"] or "") if row else "",
                    sha256=(row["sha256"] or "") if row else "",
                    downloadedAt=task_mapper.iso(row["created_at"]) if row else None,
                    archivePath=row["archive_path"] if row else None,
                    archivedAt=task_mapper.iso(row["archived_at"]) if row else None,
                    error=(row["error_message"] or "") if row else "",
                    prepare=Capability(
                        allowed=not archived and not block,
                        reason="已保存到共享盘" if archived else block or "获取子采购合同并保存到共享盘",
                    ),
                )
            )
        return result
