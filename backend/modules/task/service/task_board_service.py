"""采购开票任务台：按当前节点汇总任务，并为每个任务给出六个节点的状态与下一步提示。只读。

节点判定与任务详情共用 task_mapper.steps、资料齐全规则与通知口径，保证任务台与详情页一致。
进行中的任务全部参与节点计数（需按事实逐个判定当前节点）；已完成任务只按状态计数，选中时再分页读取。
"""

from collections import Counter

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import notification_dao, task_dao
from ..mapper import task_mapper
from ..policy.board_policy import NODE_HINTS, NODE_LABELS, NODES, next_action
from ..policy.task_policy import OPEN_STATUSES
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
                )
                open_rows = task_dao.by_statuses(connection, where, OPEN_STATUSES)
                done_total = task_dao.status_counts(connection, where).get("completed", 0)
                facts = board_facts(connection, open_rows)
                if query.node == "done":
                    page_rows = task_dao.by_statuses(
                        connection,
                        where,
                        ("completed",),
                        offset=offset,
                        limit=query.pageSize,
                        newest_first=True,
                    )
                    facts.update(board_facts(connection, page_rows))
                    total = done_total
                else:
                    # 工作台按报关单阶段下钻时，保留该范围内已完成的同单任务。
                    scoped_done = (
                        task_dao.by_statuses(connection, where, ("completed",))
                        if query.stage and not query.node
                        else []
                    )
                    facts.update(board_facts(connection, scoped_done))
                    selected = [
                        row
                        for row in open_rows + scoped_done
                        if not query.node or facts[row["id"]]["node"] == query.node
                    ]
                    selected.sort(key=lambda row: (row["created_at"], row["id"]))
                    page_rows = selected[offset : offset + query.pageSize]
                    total = len(selected)
                page_ids = [row["id"] for row in page_rows]
                contacts = notification_dao.latest_sent_by_tasks(connection, page_ids)
                supplier_ids = task_dao.supplier_ids(connection, "")
        except SQLAlchemyError:
            raise ApiError(503, READ_ERROR) from None
        page_lines = [line for row in page_rows for line in facts[row["id"]]["lines"]]
        names = self.queries.names(page_rows, page_lines)
        counts = Counter(facts[row["id"]]["node"] for row in open_rows)
        counts["done"] = done_total
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

    def _item(self, row, fact, names, contact):
        node = fact["node"]
        return BoardItem(
            task=task_mapper.summary(row, fact["lines"], names, contact),
            steps=fact["steps"],
            currentNode=node,
            currentLabel=NODE_LABELS[node],
            nextAction=next_action(node, fact["missing"]),
            blockedReason=fact["blocked"],
            missing=fact["missing"],
        )
