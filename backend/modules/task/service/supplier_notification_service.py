"""保存一份合并通知，同时保留各原任务的通知版本；人工登记在同一事务确认全部成员。"""

import hashlib
import json
from datetime import UTC

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import (
    event_dao,
    notification_dao,
    notification_delivery_dao,
    supplier_group_dao,
    supplier_task_dao,
)
from ..dao.notification_scope_dao import find_scope
from ..policy.delivery_policy import ACTIVE, BLOCK_REASON
from ..policy.notification_policy import edit_block, record_block
from .basis_guard import require_current
from .delivery_state import now, require_writer
from .supplier_task_service import pending, revision
from .task_status_service import change_status


class SupplierNotificationService:
    def __init__(self, groups):
        self.groups, self.engine = groups, groups.engine

    def _rows(self, connection, anchor_id):
        rows = supplier_task_dao.by_anchor(connection, anchor_id, lock=True)
        if not rows:
            raise ApiError(404, "供应商当前开票任务不存在")
        for row in rows:
            require_current(connection, row["id"])
            if notification_delivery_dao.overlapping(connection, row["id"], ACTIVE):
                raise ApiError(409, BLOCK_REASON)
        return rows

    def save_draft(self, anchor_id, body, actor):
        require_writer(actor)
        payload = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        try:
            with transaction(self.engine, "task") as connection:
                prior = event_dao.by_request(connection, str(body.requestId))
                if prior:
                    if (
                        prior["event_type"] != "supplier_notice_scope"
                        or prior["details"].get("requestSha256") != payload
                        or prior["details"].get("anchorId") != anchor_id
                    ):
                        raise ApiError(409, "请求编号已使用且内容不同，请刷新核实")
                else:
                    rows = self._rows(connection, anchor_id)
                    if revision(connection, rows) != body.scopeRevision:
                        raise ApiError(409, "任务、合同或通知范围已变化，请刷新后重新保存")
                    selected = pending(connection, rows)
                    if not selected:
                        raise ApiError(409, "当前供应商任务已通知或进入收票阶段")
                    at, members = now(), []
                    binding = supplier_group_dao.by_supplier(connection, rows[0]["supplier_id"])
                    for row in selected:
                        latest = notification_dao.latest(connection, row["id"])
                        if block := edit_block(row["status"], latest["status"] if latest else None):
                            raise ApiError(409, block)
                        notification_dao.insert_version(
                            connection,
                            {
                                "task_id": row["id"],
                                "version": (latest["version"] if latest else 0) + 1,
                                "chat_id": binding["chat_id"]
                                if binding and binding["enabled"] and binding["group_name"] == body.groupName
                                else None,
                                "recipient_name": body.groupName or None,
                                "sender_name": body.employee or None,
                                "content": body.message,
                                "created_by": actor,
                            },
                            at,
                        )
                        members.append(
                            {
                                "taskId": row["id"],
                                "notificationId": notification_dao.latest(connection, row["id"])["id"],
                            }
                        )
                    root = selected[0]
                    event_dao.append(
                        connection,
                        {
                            "task_id": root["id"],
                            "from_status": root["status"],
                            "to_status": root["status"],
                            "event_type": "supplier_notice_scope",
                            "reason": f"保存供应商合并通知，包含 {len(members)} 个原任务",
                            "actor": actor,
                            "request_id": str(body.requestId),
                            "details": {
                                "anchorId": anchor_id,
                                "taskId": root["id"],
                                "notificationId": members[0]["notificationId"],
                                "members": members,
                                "requestSha256": payload,
                            },
                        },
                        at,
                    )
        except SQLAlchemyError:
            raise ApiError(409, "合并通知保存结果待核实，请刷新原任务；不会自动重放") from None
        return self.groups.detail(anchor_id)

    def record(self, anchor_id, body, actor):
        require_writer(actor)
        sent_at = body.sentAt.astimezone(UTC).replace(tzinfo=None) if body.sentAt.tzinfo else None
        try:
            with transaction(self.engine, "task") as connection:
                rows = self._rows(connection, anchor_id)
                scopes = [
                    find_scope(connection, row["id"], notice["id"])
                    for row in rows
                    if (notice := notification_dao.latest(connection, row["id"]))
                ]
                row_ids = {row["id"] for row in rows}
                pending_ids = {row["id"] for row in pending(connection, rows)}
                candidates = [
                    value
                    for value in scopes
                    if value and all(member["taskId"] in row_ids for member in value["members"])
                ]
                scope = next(
                    (
                        value
                        for value in candidates
                        if {member["taskId"] for member in value["members"]} == pending_ids
                    ),
                    None,
                )
                if scope is None and candidates:
                    scope = max(candidates, key=lambda value: value["notificationId"])
                if not scope:
                    raise ApiError(409, "请先保存供应商合并通知")
                selected = [
                    row for row in rows if row["id"] in {member["taskId"] for member in scope["members"]}
                ]
                current = {member["taskId"]: member["notificationId"] for member in scope["members"]}
                latest = {row["id"]: notification_dao.latest(connection, row["id"]) for row in selected}
                if any(not value or value["id"] != current[key] for key, value in latest.items()):
                    raise ApiError(409, "合并通知版本已变化，请重新保存")
                if latest[scope["taskId"]]["version"] != body.revision:
                    raise ApiError(409, "合并通知版本已变化，请刷新后登记")
                if not body.confirmed or not body.note.strip() or sent_at is None:
                    raise ApiError(400, "请确认实际已通知、填写说明并提供带时区的发送时间")
                same = all(
                    value["status"] == "sent"
                    and value["channel"] == "manual"
                    and value["sent_at"] == sent_at
                    and value["note"] == body.note.strip()
                    for value in latest.values()
                )
                if not same:
                    if {row["id"] for row in pending(connection, rows)} != set(current):
                        raise ApiError(409, "待通知任务范围已变化，请重新保存合并通知后登记")
                    if revision(connection, rows) != body.scopeRevision:
                        raise ApiError(409, "合并范围或通知状态已变化，请刷新后登记")
                    for row in selected:
                        notice = latest[row["id"]]
                        if block := record_block(row["status"], notice):
                            raise ApiError(409, block)
                        if not row["created_at"] <= sent_at <= now():
                            raise ApiError(400, "发送时间须介于所有任务生成时间和当前时间之间")
                        notification_dao.mark_sent(
                            connection,
                            notice["id"],
                            {"sent_by": actor, "sent_at": sent_at, "note": body.note.strip()},
                            now(),
                        )
                        change_status(connection, row, "awaiting_invoice", actor, body.note.strip(), now())
        except SQLAlchemyError:
            raise ApiError(409, "合并通知登记结果待核实，请刷新；不会重复登记") from None
        return self.groups.detail(anchor_id)
