"""开票跟进查询：任务列表（按供应商或报关单分组分页）与任务详情。"""

from collections import Counter

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import notification_dao, task_dao, task_line_dao
from ..dao.notification_scope_dao import match_scope
from ..mapper import document_mapper, notification_mapper, task_detail_mapper, task_mapper
from ..policy.delivery_policy import BLOCK_REASON, LABELS, submit_reason
from ..policy.stage_policy import declaration_stage
from ..policy.task_policy import SUPERSEDED_REASON, missing_identity_reasons
from ..vo.capability import Capability
from ..vo.task_vo import SupplierOption, TaskDetail, TaskDocument, TaskGroup, TaskList
from .task_detail_reader import read_details

READ_ERROR = "开票任务读取失败，请检查业务数据库及迁移状态"


class TaskService:
    def __init__(self, engine, directory, contracts=None, archive=None, settings=None):
        self.engine, self.directory = engine, directory
        self.contracts, self.archive = contracts, archive
        self.settings = settings

    def browse(self, query):
        found = (
            self.directory.search(query.keyword) if query.keyword else {"supplier_ids": [], "order_ids": []}
        )
        declaration_ids = (
            set(self.directory.declaration_ids_created(query.createdFrom, query.createdTo))
            if query.createdFrom
            else None
        )
        try:
            with self.engine.connect() as connection:
                if query.stage:
                    declaration_ids = self.filter_declarations_by_stage(
                        connection, query.stage, declaration_ids, query.account
                    )
                where = task_dao.conditions(
                    scope=query.status,
                    account=query.account,
                    keyword=query.keyword,
                    supplier_ids=found["supplier_ids"],
                    order_ids=found["order_ids"],
                    supplier_id=int(query.supplierId) if query.supplierId else None,
                    declaration_ids=declaration_ids,
                )
                offset = (query.page - 1) * query.pageSize
                total, keys = task_dao.group_page(connection, where, query.groupBy, offset, query.pageSize)
                rows = task_dao.in_groups(connection, where, query.groupBy, keys)
                lines = task_line_dao.by_tasks(connection, [row["id"] for row in rows])
                contacts = notification_dao.latest_sent_by_tasks(connection, [row["id"] for row in rows])
                status_counts = task_dao.status_counts(connection, where)
                accounts = task_dao.accounts(connection)
                supplier_ids = task_dao.supplier_ids(connection, query.account)
        except SQLAlchemyError:
            raise ApiError(503, READ_ERROR) from None
        names = self.names(rows, lines)
        groups = [self._group(query.groupBy, key, rows, lines, names, contacts) for key in keys]
        return TaskList(
            groupBy=query.groupBy,
            groups=groups,
            counts=task_mapper.counts(status_counts),
            accounts=accounts,
            suppliers=self.supplier_options(supplier_ids),
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (total + query.pageSize - 1) // query.pageSize),
        )

    def filter_declarations_by_stage(self, connection, stage, declaration_ids, account=""):
        """两种查询入口共用报关单最慢阶段口径，不按单个任务状态替代。"""
        statuses = task_dao.declaration_statuses(connection, account)
        staged = {key for key, value in statuses.items() if declaration_stage(value) == stage}
        return staged if declaration_ids is None else declaration_ids & staged

    def supplier_options(self, supplier_ids):
        found = self.directory.describe(supplier_ids=supplier_ids)["suppliers"] if supplier_ids else {}
        options = [
            SupplierOption(id=str(key), name=(found.get(key) or {}).get("name") or f"供应商 {key}")
            for key in supplier_ids
        ]
        return sorted(options, key=lambda option: (option.name, int(option.id)))

    def names(self, tasks, lines):
        names = self.directory.describe(
            supplier_ids=[task["supplier_id"] for task in tasks if task["supplier_id"]],
            company_ids=[task["company_id"] for task in tasks if task["company_id"]],
            order_ids=[line["purchase_order_id"] for line in lines],
            line_ids=[line["purchase_line_id"] for line in lines],
        )
        names["declarations"] = self.directory.declarations(
            [task["customs_declaration_id"] for task in tasks]
        )
        return names

    def _group(self, group_by, key, rows, lines, names, contacts):
        column = "supplier_id" if group_by == "supplier" else "customs_declaration_id"
        selected = [row for row in rows if row[column] == key]
        summaries = [
            task_mapper.summary(
                row, [line for line in lines if line["task_id"] == row["id"]], names, contacts.get(row["id"])
            )
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

    def detail(self, task_id, *, scope_member=False):
        try:
            with self.engine.connect() as connection:
                task = task_dao.get(connection, task_id)
                if task is None:
                    raise ApiError(404, "开票任务不存在")
                details, _ = self.details(connection, [task], scope_member=scope_member)
                return details[0]
        except SQLAlchemyError:
            raise ApiError(503, READ_ERROR) from None

    def details(self, connection, rows, *, scope_member=True):
        data = read_details(connection, rows)
        names = self.names(rows, data["lines"])
        details = []
        for row in rows:
            task_data = data["tasks"][row["id"]]
            latest = data["latest"].get(row["id"])
            scope = (
                match_scope(data["scopes"].get(row["id"], []), row["id"], latest["id"])
                if latest and not scope_member
                else None
            )
            details.append(self._detail(task_data, names, data["signed"], scope=scope))
        return details, data

    def order_ids(self, lines):
        return sorted({line["purchase_order_id"] for line in lines})

    def _detail(self, data, names, signed, *, scope=None):
        task, lines = data["task"], data["lines"]
        order_ids = self.order_ids(lines)
        summary = task_mapper.summary(task, lines, names, data["contact"])
        documents = self._documents(
            task, self.order_ids(lines), data["documents"], names, data["contract_jobs"]
        )
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
        block = data["basis_reason"]
        latest = data["notifications"][0] if data["notifications"] else None
        if (
            data["deliveries"]
            and latest
            and latest["status"] != "sent"
            and data["deliveries"][0]["notification_id"] == latest["id"]
        ):
            notification.statusLabel = LABELS[data["deliveries"][0]["status"]]
        send_reason = submit_reason(task, latest, binding, self.settings, data["delivery_blocked"], block)
        if (
            not send_reason
            and latest
            and any(row["notification_id"] == latest["id"] for row in data["deliveries"])
        ):
            send_reason = "该版本已有执行记录，明确失败后请先保存新版本"
        notification.send = Capability(
            allowed=not send_reason, reason=send_reason or "预览正文和合同，提交后等待群主确认"
        )
        if data["delivery_blocked"]:
            notification.edit = Capability(reason=BLOCK_REASON)
            notification.record = Capability(reason=BLOCK_REASON)
        if block and not superseded:
            for document in documents:
                document.prepare = Capability(allowed=False, reason=block)
            notification.edit = Capability(allowed=False, reason=block)
            notification.record = Capability(allowed=False, reason=block)
        if scope and len(scope["members"]) > 1:
            reason = "该通知已按供应商合并，请切换供应商合并视图办理"
            notification.edit = Capability(reason=reason)
            notification.record = Capability(reason=reason)
            notification.send = Capability(reason=reason)
        prepare_reason = next((doc.prepare.reason for doc in documents if not doc.prepare.allowed), "")
        completion = document_mapper.completion(order_ids, documents, data["declaration_documents"], signed)
        detail = TaskDetail(
            task=summary,
            lines=task_mapper.lines(lines, names, task["currency"]),
            reasons=missing_identity_reasons(task["supplier_id"], task["company_id"], task["currency"]),
            sourceStatus="superseded" if superseded else "current",
            sourceMessage=SUPERSEDED_REASON
            if superseded
            else block or "任务按财务审核通过时冻结的应开数量和金额跟进。",
            prepare=Capability(
                allowed=any(doc.prepare.allowed for doc in documents),
                reason="子采购合同已保存到共享盘"
                if ready
                else prepare_reason or "获取子采购合同并保存到共享盘",
            ),
            notify=notification.send,
            compare=Capability(
                allowed=not superseded and not block,
                reason=block or "在发票比对页审核比对建议；通过或取消后自动更新任务行已收与任务状态。",
            ),
            steps=task_mapper.steps(
                task["status"],
                ready,
                bool(data["notifications"] and data["notifications"][0]["status"] == "sent"),
                notification.statusLabel,
                completion.reason,
                completion.missing,
            ),
            documents=documents,
            declarationDocuments=document_mapper.declaration_documents(
                data["declaration_documents"], task, self._declaration_unavailable()
            ),
            signedContracts=document_mapper.signed_contracts(order_ids, signed, names),
            completion=completion,
            downloadEnvironment=self.contracts.environment if self.contracts else "",
            notification=notification,
            events=task_mapper.events(data["events"]),
        )
        return task_detail_mapper.sections(detail)

    def _declaration_unavailable(self):
        if self.archive is None or self.archive.root is None:
            return "合同共享盘路径尚未配置"
        if self.contracts is None:
            return "报关资料下载接口尚未配置"
        return self.contracts.declaration_unavailable_reason()

    def _documents(self, task, order_ids, rows, names, jobs):
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
            job = jobs.get(order_id) or {}
            number = names["orders"].get(order_id) or ""
            archived = bool(row and row["status"] == "archived")
            block = unavailable or ("子采购单编号缺失" if not number else "")
            result.append(
                TaskDocument(
                    taskId=str(task["id"]),
                    recordNumber=task["record_no"] or "",
                    declarationNumber=(
                        names.get("declarations", {}).get(task["customs_declaration_id"]) or {}
                    ).get("declaration_no")
                    or "",
                    orderId=str(order_id),
                    orderNumber=number,
                    status="ready"
                    if archived
                    else "failed"
                    if (row and row["status"] == "failed") or job.get("status") == "failed"
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
                    error=""
                    if archived
                    else ((row or {}).get("error_message") or job.get("error_message") or ""),
                    prepare=Capability(
                        allowed=not archived and not block,
                        reason="已保存到共享盘" if archived else block or "获取子采购合同并保存到共享盘",
                    ),
                )
            )
        return result
