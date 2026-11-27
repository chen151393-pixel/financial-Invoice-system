"""供应商合并详情：合并办理视图，原任务、审核、合同归属与收票台账均保留。"""

import hashlib
import json
from collections import defaultdict

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import document_dao, notification_dao, supplier_task_dao, task_line_dao
from ..dao.notification_scope_dao import match_scope
from ..mapper.task_detail_mapper import sections
from ..policy.notification_policy import EDITABLE_STATUSES, default_message
from ..policy.supplier_task_policy import apply_status, capability, steps_and_node, summary
from ..vo.capability import Capability
from .task_service import READ_ERROR


def revision(connection, rows, *, lines=None, documents=None, latest=None):
    ids = [row["id"] for row in rows]
    lines = task_line_dao.by_tasks(connection, ids) if lines is None else lines
    documents = document_dao.by_tasks(connection, ids) if documents is None else documents
    latest = notification_dao.latest_by_tasks(connection, ids) if latest is None else latest
    own_lines, own_documents = defaultdict(list), defaultdict(list)
    for line in lines:
        own_lines[line["task_id"]].append([line["id"], line["purchase_basis_id"]])
    for doc in documents:
        own_documents[doc["task_id"]].append([doc["id"], doc["status"], doc["sha256"]])
    values = []
    for row in rows:
        notice = latest.get(row["id"])
        values.append(
            {
                "id": row["id"],
                "status": row["status"],
                "review": row["review_id"],
                "revision": row["review_revision"],
                "notice": [notice["id"], notice["status"]] if notice else None,
                "basis": own_lines[row["id"]],
                "documents": own_documents[row["id"]],
            }
        )
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def pending(connection, rows, *, latest=None):
    if latest is None:
        latest = notification_dao.latest_by_tasks(connection, [row["id"] for row in rows])
    return [
        row
        for row in rows
        if row["status"] in EDITABLE_STATUSES and (latest.get(row["id"]) or {}).get("status") != "sent"
    ]


class SupplierTaskService:
    def __init__(self, tasks):
        self.tasks, self.engine = tasks, tasks.engine

    def detail(self, anchor_id, *, completed=False):
        try:
            with self.engine.connect() as connection:
                rows = supplier_task_dao.by_anchor(connection, anchor_id, completed=completed)
                if not rows:
                    raise ApiError(404, "供应商当前开票任务不存在，请返回列表刷新")
                details, data = self.tasks.details(connection, rows)
                token = revision(
                    connection, rows, lines=data["lines"], documents=data["documents"], latest=data["latest"]
                )
                waiting = pending(connection, rows, latest=data["latest"])
        except SQLAlchemyError:
            raise ApiError(503, READ_ERROR) from None
        raw_lines = data["lines"]
        by_id = {int(detail.task.id): detail for detail in details}
        base = details[0].model_copy(deep=True)
        base.grouped, base.scopeRevision = True, token
        base.memberTasks = [detail.task for detail in details]
        base.task = summary(base.memberTasks, raw_lines)
        base.steps, node = steps_and_node([detail.steps for detail in details])
        apply_status(base.task, node)
        base.steps[2].description = "本供应商已全部通知" if base.steps[2].state == "done" else "待通知供应商"
        base.lines = [
            line.model_copy(update={"taskId": detail.task.id}) for detail in details for line in detail.lines
        ]
        documents = {}
        declarations = {}
        signed = {}
        for detail in details:
            for doc in detail.documents:
                candidate = doc.model_copy(update={"taskId": detail.task.id})
                if doc.orderId not in documents or doc.status == "ready":
                    documents[doc.orderId] = candidate
            for doc in detail.declarationDocuments:
                declarations[(detail.task.recordNumber, doc.type)] = doc.model_copy(
                    update={"taskId": detail.task.id, "recordNumber": detail.task.recordNumber}
                )
            signed.update({doc.orderId: doc for doc in detail.signedContracts})
        base.documents, base.declarationDocuments, base.signedContracts = (
            list(documents.values()),
            list(declarations.values()),
            list(signed.values()),
        )
        base.reasons = list(dict.fromkeys(reason for detail in details for reason in detail.reasons))
        missing = list(
            dict.fromkeys(
                name for detail in details if detail.completion for name in detail.completion.missing
            )
        )
        base.completion = base.completion.model_copy(
            update={
                "ready": not missing,
                "missing": missing,
                "reason": "资料已全部到齐" if not missing else "尚缺：" + "、".join(missing),
            }
        )
        base.steps[-1].description = "已完成" if node == "done" else base.completion.reason
        base.events = sorted(
            [
                event.model_copy(update={"reason": f"{detail.task.recordNumber}：{event.reason}"})
                for detail in details
                for event in detail.events
            ],
            key=lambda event: event.at,
        )
        base.sourceMessage = next(
            (detail.sourceMessage for detail in details if not detail.compare.allowed),
            "同一供应商的资料与通知合并办理，原审核与收票依据逐项保留。",
        )
        base.prepare = Capability(
            allowed=any(doc.prepare.allowed for doc in base.documents),
            reason="获取各子采购合同并保存到原报关单目录",
        )
        base.compare = capability([detail.compare for detail in details])
        self._notification(base, rows, by_id, waiting, data)
        return sections(base)

    def _notification(self, base, rows, by_id, waiting, data):
        selected = waiting or rows
        anchor = min(selected, key=lambda row: row["id"])
        root_detail = by_id[anchor["id"]]
        latest = data["latest"].get(anchor["id"])
        scope = (
            match_scope(data["scopes"].get(anchor["id"], []), anchor["id"], latest["id"]) if latest else None
        )
        expected = {row["id"] for row in selected}
        valid = bool(
            scope
            and {member["taskId"] for member in scope["members"]} == expected
            and all(
                (data["latest"].get(member["taskId"]) or {}).get("id") == member["notificationId"]
                for member in scope["members"]
            )
        )
        if valid:
            anchor_id = scope["taskId"]
            root_detail = by_id.get(anchor_id, root_detail)
        else:
            anchor_id = anchor["id"]
        notice = root_detail.notification.model_copy(deep=True)
        notice.history = sorted(
            [
                event.model_copy(update={"taskId": detail.task.id, "recordNumber": detail.task.recordNumber})
                for detail in by_id.values()
                for event in detail.notification.history
            ],
            key=lambda event: event.at,
            reverse=True,
        )
        orders = sorted({number for row in selected for number in by_id[row["id"]].task.orderNumbers})
        records = "、".join(dict.fromkeys(by_id[row["id"]].task.recordNumber for row in selected))
        notice.defaultMessage = default_message(base.task.supplier, base.task.company, orders, records)
        if not valid and waiting:
            notice.message = notice.defaultMessage
            notice.revision = 0
        notice.taskIds = [str(row["id"]) for row in selected]
        base.notificationDocuments = [
            doc.model_copy(update={"taskId": str(row["id"])})
            for row in selected
            for doc in by_id[row["id"]].documents
        ]
        notice.attachments = list(
            dict.fromkeys(doc.filename for doc in base.notificationDocuments if doc.status == "ready")
        )
        total = len(base.notificationDocuments)
        archived = sum(doc.status == "ready" for doc in base.notificationDocuments)
        contract_reason = f"子采购合同已归档 {archived} / {total} 份。"
        if total and archived == total:
            contract_reason += "全部对应子采购合同已归档，发送时请附上。"
        else:
            contract_reason += "合同尚未齐全，请先完成归档。"
        notice.scopeReason = (
            f"本次通知覆盖 {len(selected)} 个原任务、{len(orders)} 张子采购单。{contract_reason}"
            if waiting
            else "当前任务均已通知或进入收票阶段，保留通知记录，只读。"
        )
        notice.edit = (
            capability([by_id[row["id"]].notification.edit for row in selected])
            if waiting
            else Capability(reason=notice.scopeReason)
        )
        notice.record = (
            capability([by_id[row["id"]].notification.record for row in selected])
            if valid and waiting
            else Capability(reason="请先保存本次合并通知，再登记实际发送结果")
        )
        notice.send = (
            capability([by_id[row["id"]].notification.send for row in selected])
            if valid and waiting
            else Capability(reason="请先保存本次合并通知，再预览全部合同并提交")
        )
        base.notification, base.notificationTaskId = notice, str(anchor_id)
        base.notify = notice.send
