"""审核事务内生成任务，查询复用已保存的范围，外部来源核验在事务外进行。"""

import hashlib
import json
import time
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.integrations.contract_archive import ContractArchive

from . import dao, notification_dao, notification_service, task_dao, task_mapper, task_policy
from .task_vo import TaskCapability, TaskDetail, TaskGroup, TaskList


def generate_tasks(connection, preview, payload, owner, now):
    """仅在审核头版本成功递增后调用，沿用同一事务及审核头锁。"""
    groups = task_policy.split_scope(payload, preview["account"], preview["declaration_id"])
    record_number = (
        payload["display"]["recordNumber"]
        if payload.get("source") == "database"
        else payload["group"]["recordNumber"]
    )
    values = [
        {
            **group,
            "id": str(uuid.uuid4()),
            "owner": owner,
            "account": preview["account"],
            "declaration_id": preview["declaration_id"],
            "snapshot_id": preview["id"],
            "review_revision": preview["revision"] + 1,
            "record_number": record_number,
            "status": "documents_pending",
            "created_at": now,
            "payload": json.dumps(group["payload"], ensure_ascii=False),
        }
        for group in groups
    ]
    task_dao.replace_revision(connection, owner, preview["account"], preview["declaration_id"], values)


class InvoiceTaskService:
    def __init__(self, engine, local_source, contract_source=None, archive=None):
        self.engine, self.local_source = engine, local_source
        self.contract_source = contract_source
        self.archive = archive or ContractArchive(None)

    def browse(self, query, owner):
        try:
            # 分组、列表及统计必须来自同一个版本；应用库其他写入仍保留原隔离级别。
            isolation = "REPEATABLE READ" if self.engine.dialect.name == "mysql" else "SERIALIZABLE"
            with self.engine.connect().execution_options(isolation_level=isolation) as connection:
                keys, rows, counts, accounts, total = task_dao.browse(connection, owner, query)
        except SQLAlchemyError:
            raise ApiError(503, "开票任务读取失败，请检查应用数据库并执行最新迁移") from None
        column = "supplier_key" if query.groupBy == "supplier" else "declaration_key"
        groups = []
        for key in keys:
            selected = [row for row in rows if row[column] == key["key"]]
            groups.append(
                TaskGroup(
                    id=key["key"],
                    label=selected[0]["supplier" if query.groupBy == "supplier" else "record_number"],
                    account=selected[0]["account"],
                    counts=task_mapper.counts(Counter(row["status"] for row in selected)),
                    tasks=[task_mapper.summary(row) for row in selected],
                )
            )
        return TaskList(
            groupBy=query.groupBy,
            groups=groups,
            counts=task_mapper.counts(counts),
            accounts=accounts,
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (total + query.pageSize - 1) // query.pageSize),
        )

    def _row(self, task_id, owner):
        try:
            with self.engine.connect() as connection:
                row = task_dao.detail(connection, owner, task_id)
        except SQLAlchemyError:
            raise ApiError(503, "开票任务读取失败，请检查应用数据库") from None
        if row is None:
            raise ApiError(404, "开票任务不存在或无权访问")
        return row

    def detail(self, task_id, owner):
        row = self._row(task_id, owner)
        payload = json.loads(row["payload"])
        source_status, source_message = self._freshness(row, owner)
        environment = self.contract_source.environment if self.contract_source else ""
        reason = (
            source_message
            if source_status != "current"
            else (
                self.contract_source.unavailable_reason()
                if self.contract_source
                else "子采购合同下载接口尚未配置"
            )
        )
        with self.engine.connect() as connection:
            saved = {item["order_id"]: item for item in task_dao.document_rows(connection, task_id)}
        docs = []
        for order in payload["orders"]:
            doc = saved.get(order["id"])
            block = (
                (source_message if source_status != "current" else "")
                or ("合同共享盘路径尚未配置" if self.archive.root is None else "")
                or (reason if not doc else "")
                or ("审核快照缺少子采购单编号" if not order["number"] else "")
            )
            archived = bool(doc and doc["archived_at"])
            docs.append(
                {
                    "orderId": order["id"],
                    "orderNumber": order["number"],
                    "status": "ready" if archived else "archive_pending" if doc else "pending",
                    "archivePath": doc["archive_path"] if doc else None,
                    "archivedAt": datetime.fromtimestamp(doc["archived_at"], UTC).isoformat()
                    if archived
                    else None,
                    "environment": doc["environment"] if doc else environment,
                    "nsId": doc["ns_id"] if doc else "",
                    "filename": doc["filename"] if doc else "",
                    "sha256": doc["sha256"] if doc else "",
                    "downloadedAt": datetime.fromtimestamp(doc["downloaded_at"], UTC).isoformat()
                    if doc
                    else None,
                    "prepare": TaskCapability(
                        allowed=not block and not archived,
                        reason="已保存到共享盘"
                        if archived
                        else block
                        or ("原件已暂存，待保存到共享盘" if doc else "获取子采购合同并保存到共享盘"),
                    ),
                }
            )
        ready = bool(docs) and all(doc["status"] == "ready" for doc in docs)
        historical = row["status"] == "superseded"
        with self.engine.connect() as connection:
            history = notification_dao.history(connection, task_id)
        notification = notification_service.view(row, history, source_status, source_message, ready)
        recorded = bool(notification.history and notification.history[0].sentAt)
        return TaskDetail(
            task=task_mapper.summary(row),
            lines=payload["lines"],
            reasons=[] if row["currency"] else ["来源未提供币种，以子采购订单原件为准；不影响资料下载。"],
            sourceStatus=source_status,
            sourceMessage=source_message,
            downloadEnvironment=environment,
            notification=notification,
            documents=docs,
            prepare=TaskCapability(
                allowed=any(doc["prepare"].allowed for doc in docs),
                reason=reason
                or ("子采购合同已保存到共享盘" if ready else "财务审核已通过，无需再次确认开票范围。"),
            ),
            notify=notification.send,
            compare=TaskCapability(reason="开票任务与收票、发票比对的关联尚未接入。"),
            steps=[
                {"label": "财务审核", "description": "审核已通过", "state": "done"},
                {
                    "label": "资料准备",
                    "description": "原件已备齐" if ready else "保存子采购合同到共享盘",
                    "state": "done" if ready else "waiting" if historical else "current",
                },
                {
                    "label": "通知供应商",
                    "description": notification.statusLabel,
                    "state": "done" if recorded else "current" if ready and not historical else "waiting",
                },
                {
                    "label": "等待收票",
                    "description": "等待供应商开票",
                    "state": "current" if recorded and not historical else "waiting",
                },
                {"label": "发票比对", "description": "收票后核对", "state": "waiting"},
                {"label": "完成", "description": "尚未完成", "state": "waiting"},
            ],
        )

    def save_notification(self, task_id, body, owner, *, record=False):
        row = self._row(task_id, owner)
        status, reason = self._freshness(row, owner)
        if status != "current":
            raise ApiError(409, reason)
        try:
            with self.local_source.locked_review(owner, row["account"], row["declaration_id"]) as data:
                sources = list(data["review_sources"].values())
                if len(sources) != 1 or sources[0]["digest"] != row["digest"]:
                    raise ApiError(409, "审核来源已变化，请重新审核后操作")
                with self.engine.begin() as connection:
                    head = dao.head(connection, owner, row["account"], row["declaration_id"])
                    current = task_dao.detail(connection, owner, task_id, lock=True)
                    if head["snapshot_id"] != row["snapshot_id"] or current["status"] == "superseded":
                        raise ApiError(409, "任务已被新审核版本替代")
                    notification_service.save(connection, current, body, owner, record=record)
        except SQLAlchemyError:
            raise ApiError(409, "通知未能保存，请刷新核实最新版本后操作") from None
        return self.detail(task_id, owner)

    def prepare_document(self, task_id, order_id, owner):
        row = self._row(task_id, owner)
        payload = json.loads(row["payload"])
        order = next((item for item in payload["orders"] if item["id"] == order_id), None)
        if order is None:
            raise ApiError(404, "子采购单不属于此任务")
        status, reason = self._freshness(row, owner)
        if status != "current":
            raise ApiError(409, reason)
        if self.archive.root is None:
            raise ApiError(503, "合同共享盘路径尚未配置")
        with self.engine.connect() as connection:
            cached = task_dao.document_file(connection, task_id, order_id)
        if cached:
            return self._archive_document(row, order, cached, owner)
        if self.contract_source is None:
            raise ApiError(503, "子采购合同下载接口尚未配置")
        reason = self.contract_source.unavailable_reason()
        if reason:
            raise ApiError(503, reason)
        # 网络下载在事务和来源锁之外；成功后再次核验快照，失败不推进流程。
        document = self.contract_source.download(order["number"], row["supplier"], row["record_number"])
        try:
            with self.local_source.locked_review(owner, row["account"], row["declaration_id"]) as data:
                sources = list(data["review_sources"].values())
                if len(sources) != 1 or sources[0]["digest"] != row["digest"]:
                    raise ApiError(409, "下载期间审核来源发生变化，请重新审核；文件未入库")
                with self.engine.begin() as connection:
                    # 与审核相同的加锁顺序，防止旧任务覆盖新版本或并发重复入库。
                    head = dao.head(connection, owner, row["account"], row["declaration_id"])
                    current = task_dao.detail(connection, owner, task_id, lock=True)
                    if head["snapshot_id"] != row["snapshot_id"] or current["status"] == "superseded":
                        raise ApiError(409, "任务已被新审核版本替代，文件未入库")
                    saved = task_dao.document_rows(connection, task_id)
                    if not any(item["order_id"] == order_id for item in saved):
                        task_dao.save_document(
                            connection,
                            {
                                **document,
                                "task_id": task_id,
                                "order_id": order_id,
                                "sha256": hashlib.sha256(document["content"]).hexdigest(),
                                "downloaded_at": int(time.time()),
                            },
                        )
        except SQLAlchemyError:
            raise ApiError(503, "合同保存失败，流程未推进；请检查应用数据库") from None
        with self.engine.connect() as connection:
            cached = task_dao.document_file(connection, task_id, order_id)
        return self._archive_document(row, order, cached, owner)

    def _archive_document(self, row, order, cached, owner):
        if cached["archived_at"]:
            return self.detail(row["id"], owner)
        # 共享盘 I/O 不占用数据库锁；失败时保留暂存原件，下一次不重复调用 NS。
        path, filename = self.archive.save(
            order["number"], row["supplier"], cached["downloaded_at"], cached["content"]
        )
        try:
            with self.local_source.locked_review(owner, row["account"], row["declaration_id"]) as data:
                sources = list(data["review_sources"].values())
                fresh = len(sources) == 1 and sources[0]["digest"] == row["digest"]
                with self.engine.begin() as connection:
                    head = dao.head(connection, owner, row["account"], row["declaration_id"])
                    current = task_dao.detail(connection, owner, row["id"], lock=True)
                    active = (
                        fresh
                        and head["snapshot_id"] == row["snapshot_id"]
                        and current["status"] != "superseded"
                    )
                    saved = task_dao.document_rows(connection, row["id"])
                    complete = (
                        active
                        and len(saved) == len(json.loads(row["payload"])["orders"])
                        and all(item["archived_at"] or item["order_id"] == order["id"] for item in saved)
                    )
                    task_dao.archive_document(
                        connection, row["id"], order["id"], path, filename, int(time.time()), complete
                    )
            if not active:
                raise ApiError(409, "文件已保存到共享盘，但审核来源或版本已变化，未推进任务；请重新核对")
        except SQLAlchemyError:
            raise ApiError(
                503, "文件已保存到共享盘，但保存记录失败；请重试，同内容文件不会重复覆盖"
            ) from None
        return self.detail(row["id"], owner)

    def _freshness(self, row, owner):
        if row["status"] == "superseded":
            return "superseded", "此任务已被新审核版本替代，仅供追溯。"
        source = json.loads(row["snapshot_payload"])
        if source.get("source") != "database" or self.local_source is None:
            return "unavailable", "当前只展示审核时快照，尚未核验最新来源。"
        try:
            data = self.local_source.read_one(owner, row["account"], row["declaration_id"])
        except ApiError:
            return "unavailable", "当前来源无法读取，不能据此继续开票；请检查来源后重新核对。"
        sources = list(data["review_sources"].values())
        if len(sources) != 1 or sources[0]["digest"] != row["digest"]:
            return "changed", "审核后来源已变化或被停用，请返回财务核对重新审核。"
        return "current", "当前来源与生成任务时的审核快照一致。"
