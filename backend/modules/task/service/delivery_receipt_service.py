"""查询本地执行及渠道回执；关闭创建开关仍允许核实，不自动重发。"""

from datetime import timedelta

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import notification_dao, task_dao
from ..dao import notification_delivery_dao as dao
from ..mapper.delivery_mapper import view
from ..policy.delivery_policy import receipt
from ..vo.delivery_vo import DeliveryList
from .basis_guard import reason as basis_reason
from .delivery_snapshot import evidence_warning
from .delivery_state import now, owned, require_writer, transition
from .task_status_service import change_status


class DeliveryReceiptService:
    def __init__(self, engine, channel):
        self.engine, self.channel = engine, channel

    def history(self, task_id):
        with self.engine.connect() as connection:
            if task_dao.get(connection, task_id) is None:
                raise ApiError(404, "开票任务不存在")
            return DeliveryList(items=[view(row) for row in dao.history(connection, task_id)])

    def read(self, task_id, delivery_id):
        with self.engine.connect() as connection:
            return owned(connection, task_id, delivery_id)

    def _claim_refresh(self, task_id, delivery_id, actor):
        with transaction(self.engine, "task") as connection:
            task = task_dao.get(connection, task_id, lock=True)
            row = owned(connection, task_id, delivery_id, lock=True)
            at = now()
            if row["status"] in ("preparing", "submitting") and row["lease_expires_at"] <= at:
                target = "failed" if row["status"] == "preparing" else "unknown"
                transition(
                    connection,
                    task,
                    row,
                    target,
                    actor,
                    {
                        "error_message": "创建前执行已中断，请保存新通知版本"
                        if target == "failed"
                        else "创建阶段中断，结果待核实；禁止重复提交",
                        "lease_token": "expired",
                    },
                )
                row = dao.get(connection, row["id"])
            if row["status"] != "pending_confirmation" or not row["channel_message_id"]:
                return row, False
            if row["next_check_at"] and row["next_check_at"] > at:
                return row, False
            dao.update_delivery(connection, row["id"], {"next_check_at": at + timedelta(seconds=30)}, at)
            return row, True

    def refresh(self, task_id, body, actor):
        require_writer(actor)
        try:
            row, claimed = self._claim_refresh(task_id, body.deliveryId, actor)
            if not claimed:
                return view(row)
            try:
                results = self.channel.results(
                    row["corp_id"], row["channel_message_id"], row["sender_userid"]
                )
                self._apply(task_id, row, results, actor)
            except ApiError as error:
                self._query_error(task_id, row, error)
            return view(self.read(task_id, row["id"]))
        except SQLAlchemyError:
            raise ApiError(409, "回执保存未完成，请稍后查询原记录；不会重新创建群发") from None

    def _query_error(self, task_id, row, error):
        with transaction(self.engine, "task") as connection:
            task_dao.get(connection, task_id, lock=True)
            current = owned(connection, task_id, row["id"], lock=True)
            if current["status"] == "pending_confirmation":
                dao.update_delivery(
                    connection,
                    row["id"],
                    {
                        "error_message": error.message[:500],
                        "last_checked_at": now(),
                        "next_check_at": now() + timedelta(seconds=120),
                    },
                    now(),
                )

    def _apply(self, task_id, row, results, actor):
        targets = [item for item in results if item.get("chat_id") == row["chat_id"]]
        # 精确校验发送成员，其他群或其他成员的成功不能推进本任务。
        if any(item.get("userid") != row["sender_userid"] for item in targets):
            raise ApiError(502, "目标群回执发送成员不一致，请核实")
        target, sent_at, message = receipt(results, row["chat_id"])
        with transaction(self.engine, "task") as connection:
            task = task_dao.get(connection, task_id, lock=True)
            current = owned(connection, task_id, row["id"], lock=True)
            if current["status"] != "pending_confirmation":
                return
            block = basis_reason(connection, task_id)
            values = {
                "last_checked_at": now(),
                "error_message": evidence_warning(connection, current) or message or None,
                "channel_status": str(targets[0].get("status")) if len(targets) == 1 else None,
                "evidence_json": {
                    **current["evidence_json"],
                    "receipt": [
                        {key: item.get(key) for key in ("chat_id", "userid", "status", "send_time")}
                        for item in targets
                    ],
                },
            }
            if target:
                values["sent_at"] = sent_at
                transition(connection, task, current, target, actor, values)
                if target == "sent":
                    self._mark_notification(connection, task, current, sent_at, actor, block)
            else:
                dao.update_delivery(connection, row["id"], values, now())

    @staticmethod
    def _mark_notification(connection, task, row, sent_at, actor, block):
        frozen = row["snapshot_json"]
        notification_dao.mark_sent(
            connection,
            row["notification_id"],
            {
                "channel": "wecom",
                "channel_message_id": row["channel_message_id"],
                "chat_id": row["chat_id"],
                "recipient_name": frozen["groupName"],
                "sender_name": frozen["employee"],
                "sent_by": actor,
                "sent_at": sent_at,
                "note": "企微目标群渠道回执确认；不代表供应商已读或已开票。",
            },
            now(),
        )
        if not block and task["status"] == "notify_pending":
            change_status(connection, task, "awaiting_invoice", actor, "企微已确认目标群发送", now())
