"""采购开票任务台：按当前节点汇总任务，并为每个任务给出六个节点的状态与下一步提示。只读。

节点判定与任务详情共用 task_mapper.steps、资料齐全规则与通知口径，保证任务台与详情页一致。
进行中的任务全部参与节点计数（需按事实逐个判定当前节点）；已完成任务只按状态计数，选中时再分页读取。
"""

from collections import Counter

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import notification_dao, supplier_task_dao, task_dao
from ..mapper import task_mapper
from ..policy.board_policy import NODE_HINTS, NODE_LABELS, NODES, next_action
from ..policy.notification_group_policy import member_revision, record_block
from ..policy.supplier_task_policy import board_item as merge_board_item
from ..policy.supplier_task_policy import steps_and_node
from ..policy.task_policy import OPEN_STATUSES
from ..vo.capability import Capability
from ..vo.notification_vo import NotificationBatchTarget
from ..vo.task_vo import BoardItem, BoardNode, TaskBoard
from .board_facts import board_facts
from .task_service import READ_ERROR


class TaskBoardService:
    def __init__(self, engine, directory, queries):
        # queries：TaskService，复用供应商、子采购等名称解析与供应商筛选选项
        self.engine, self.directory, self.queries = engine, directory, queries

    def browse(self, query):
        found = (
            self.directory.search(query.keyword) if query.keyword else {"supplier_ids": [], "order_ids": []}
        )
        offset = (query.page - 1) * query.pageSize
        filters = (
            self.directory.search_task_filters(
                supplier_name=query.supplierName, purchase_order_no=query.purchaseOrderNo
            )
            if query.supplierName or query.purchaseOrderNo
            else {"supplier_ids": None, "order_ids": None}
        )
        declaration_ids = (
            set(self.directory.declaration_ids_created(query.createdFrom, query.createdTo))
            if query.createdFrom
            else None
        )
        try:
            with self.engine.connect() as connection:
                if query.stage:
                    declaration_ids = self.queries.filter_declarations_by_stage(
                        connection, query.stage, declaration_ids
                    )
                where = task_dao.conditions(
                    scope="current",
                    account="",
                    keyword=query.keyword,
                    supplier_ids=found["supplier_ids"],
                    order_ids=found["order_ids"],
                    supplier_id=int(query.supplierId) if query.supplierId else None,
                    declaration_ids=declaration_ids,
                    record_no=query.recordNo,
                    matching_supplier_ids=filters["supplier_ids"],
                    matching_order_ids=filters["order_ids"],
                )
                if query.groupBy == "supplier":
                    return self._supplier_board(connection, query, where, offset)
                open_rows = task_dao.by_statuses(connection, where, OPEN_STATUSES, heads_only=True)
                done_total = task_dao.status_counts(connection, where).get("completed", 0)
                facts = board_facts(connection, open_rows, node_only=True)
                counts = Counter(facts[row["id"]]["node"] for row in open_rows)
                counts["done"] = done_total
                if query.node == "done":
                    page_rows = task_dao.by_statuses(
                        connection,
                        where,
                        ("completed",),
                        offset=offset,
                        limit=query.pageSize,
                        newest_first=True,
                    )
                    facts.update(board_facts(connection, page_rows, node_only=True))
                    total = done_total
                else:
                    # 工作台按报关单阶段下钻时，保留该范围内已完成的同单任务。
                    scoped_done = (
                        task_dao.by_statuses(connection, where, ("completed",), heads_only=True)
                        if query.stage and not query.node
                        else []
                    )
                    facts.update(board_facts(connection, scoped_done, node_only=True))
                    selected = [
                        row
                        for row in open_rows + scoped_done
                        if not query.node or facts[row["id"]]["node"] == query.node
                    ]
                    selected.sort(key=lambda row: (row["created_at"], row["id"]))
                    page_rows = selected[offset : offset + query.pageSize]
                    total = len(selected)
                page_ids = [row["id"] for row in page_rows]
                loaded = {row["id"]: row for row in task_dao.by_ids(connection, page_ids)}
                page_rows = [loaded[task_id] for task_id in page_ids]
                facts = board_facts(connection, page_rows, node_facts=facts)
                contacts = notification_dao.latest_sent_by_tasks(connection, page_ids)
                supplier_ids = task_dao.supplier_ids(connection, "")
        except SQLAlchemyError:
            raise ApiError(503, READ_ERROR) from None
        page_lines = [line for row in page_rows for line in facts[row["id"]]["lines"]]
        names = self.queries.names(page_rows, page_lines)
        return TaskBoard(
            nodes=[
                BoardNode(key=key, label=NODE_LABELS[key], hint=NODE_HINTS[key], count=counts[key])
                for key in NODES
            ],
            openTotal=len(open_rows),
            items=[self._item(row, facts[row["id"]], names, contacts.get(row["id"])) for row in page_rows],
            suppliers=self.queries.supplier_options(supplier_ids),
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (total + query.pageSize - 1) // query.pageSize),
        )

    def _supplier_board(self, connection, query, where, offset):
        """先用轻量事实定位完整供应商分组，分页后才读取本页明细、名称与来源校验。"""
        open_rows = supplier_task_dao.expand(
            connection,
            task_dao.by_statuses(connection, where, OPEN_STATUSES, heads_only=True),
            heads_only=True,
        )
        done_rows = supplier_task_dao.expand(
            connection,
            task_dao.by_statuses(connection, where, ("completed",), heads_only=True),
            completed=True,
            heads_only=True,
        )
        rows = open_rows + done_rows
        facts = board_facts(connection, rows, node_only=True)
        groups = {}
        for row in rows:
            key = (supplier_task_dao.identity(row), row["status"] == "completed")
            groups.setdefault(key, []).append(row)
        nodes = {
            key: steps_and_node([facts[row["id"]]["steps"] for row in members])[1]
            for key, members in groups.items()
        }
        counts = Counter(nodes.values())
        selected = (
            [key for key in groups if nodes[key] == query.node]
            if query.node
            else [key for key in groups if query.stage or nodes[key] != "done"]
        )
        selected.sort(
            key=lambda key: (
                min(row["created_at"] for row in groups[key]),
                min(row["id"] for row in groups[key]),
            ),
            reverse=query.node == "done",
        )
        page_keys = selected[offset : offset + query.pageSize]
        page_ids = [row["id"] for key in page_keys for row in groups[key]]
        page_rows = task_dao.by_ids(connection, page_ids)
        loaded = {row["id"]: row for row in page_rows}
        facts = board_facts(connection, page_rows, node_facts=facts)
        lines = [line for row in page_rows for line in facts[row["id"]]["lines"]]
        names = self.queries.names(page_rows, lines)
        contacts = notification_dao.latest_sent_by_tasks(connection, page_ids)
        items = [
            merge_board_item(
                [
                    self._item(loaded[row["id"]], facts[row["id"]], names, contacts.get(row["id"]))
                    for row in groups[key]
                ],
                [line for row in groups[key] for line in facts[row["id"]]["lines"]],
            )
            for key in page_keys
        ]
        return TaskBoard(
            nodes=[
                BoardNode(key=key, label=NODE_LABELS[key], hint=NODE_HINTS[key], count=counts[key])
                for key in NODES
            ],
            openTotal=sum(node != "done" for node in nodes.values()),
            items=items,
            suppliers=self.queries.supplier_options(task_dao.supplier_ids(connection, "")),
            total=len(selected),
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (len(selected) + query.pageSize - 1) // query.pageSize),
        )

    def _item(self, row, fact, names, contact):
        node = fact["node"]
        # 来源变化的任务不能登记；未决企微通知等其余条件在提交时逐个复核
        block = record_block(row, fact)
        summary = task_mapper.summary(row, fact["lines"], names, contact)
        return BoardItem(
            task=summary,
            steps=fact["steps"],
            currentNode=node,
            currentLabel=NODE_LABELS[node],
            nextAction=next_action(node, fact["missing"]),
            blockedReason=fact["blocked"],
            missing=fact["missing"],
            notifyRecord=Capability(allowed=not block, reason=block or "线下通知供应商后可勾选批量登记。"),
            notifyTargets=[
                NotificationBatchTarget(
                    id=summary.id,
                    supplier=summary.supplier,
                    recordNumber=summary.recordNumber,
                    orderNumbers=summary.orderNumbers,
                )
            ]
            if not block
            else [],
            notifyScopeRevision=member_revision(row, fact),
        )
