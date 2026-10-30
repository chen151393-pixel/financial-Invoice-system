"""未知结果只关联渠道证据完整的唯一候选，不接受任意 msgid 或强制重置。"""

from datetime import UTC

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import task_dao
from ..mapper.delivery_mapper import view
from ..vo.delivery_vo import DeliveryCandidate, DeliveryCandidates
from .delivery_snapshot import digest
from .delivery_state import now, owned, require_writer, transition


class DeliveryReconcileService:
    def __init__(self, engine, channel, receipts):
        self.engine, self.channel, self.receipts = engine, channel, receipts

    def _candidates(self, row):
        if row["status"] != "unknown" or not row["submitted_at"]:
            return []
        start = int(row["submitted_at"].replace(tzinfo=UTC).timestamp()) - 60
        end = start + 20 * 60
        records = self.channel.records(row["corp_id"], start, end)
        media_ids = row["evidence_json"].get("mediaIds")
        if not media_ids:
            return []
        matches = []
        for item in records:
            if not self._matching_record(item, row, media_ids, start, end):
                continue
            members = self.channel.members(row["corp_id"], item["msgid"])
            if len(members) != 1 or members[0].get("userid") != row["sender_userid"]:
                continue
            results = self.channel.results(row["corp_id"], item["msgid"], row["sender_userid"])
            # 官方接口未返回未发送客户群时，缺失目标证据就继续保留 unknown。
            if (
                len(results) != 1
                or results[0].get("chat_id") != row["chat_id"]
                or results[0].get("userid") != row["sender_userid"]
            ):
                continue
            evidence = {
                "msgid": item["msgid"],
                "createTime": item["create_time"],
                "corpId": row["corp_id"],
                "chatId": row["chat_id"],
                "sender": row["sender_userid"],
                "message": row["snapshot_json"]["message"],
                "mediaIds": media_ids,
            }
            matches.append((item["msgid"], digest(evidence), evidence))
        return matches if len(matches) == 1 else []

    @staticmethod
    def _matching_record(item, row, media_ids, start, end):
        attachments = [{"msgtype": "file", "file": {"media_id": media}} for media in media_ids]
        return (
            isinstance(item.get("msgid"), str)
            and 0 < len(item["msgid"]) <= 190
            and item.get("create_type") == 0
            and type(item.get("create_time")) is int
            and start <= item["create_time"] <= end
            and item.get("text") == {"content": row["snapshot_json"]["message"]}
            and item.get("attachments") == attachments
        )

    def candidates(self, task_id, delivery_id, actor):
        require_writer(actor)
        row = self.receipts.read(task_id, delivery_id)
        matches = self._candidates(row)
        return DeliveryCandidates(
            items=[
                DeliveryCandidate(
                    candidateId=msgid,
                    evidenceSha256=sha,
                    description="正文、全部素材、创建时间、发送成员及唯一目标群一致",
                )
                for msgid, sha, _ in matches
            ],
            reason="找到唯一完整候选，请核实后关联"
            if matches
            else "未找到唯一且证据完整的记录。请群主核实并确认原群发；没有收到消息不能证明未创建，系统继续禁止重发。",
        )

    def reconcile(self, task_id, body, actor):
        require_writer(actor)
        row = self.receipts.read(task_id, body.deliveryId)
        if (
            row["status"] in ("pending_confirmation", "sent")
            and row["channel_message_id"] == body.candidateId
        ):
            return view(row)
        matches = self._candidates(row)
        if len(matches) != 1 or matches[0][:2] != (body.candidateId, body.evidenceSha256):
            raise ApiError(409, "渠道证据不完整或已变化，不能关联，请重新核实")
        try:
            with transaction(self.engine, "task") as connection:
                task = task_dao.get(connection, task_id, lock=True)
                current = owned(connection, task_id, row["id"], lock=True)
                if current["status"] != "unknown":
                    raise ApiError(409, "发送记录已变化，请刷新")
                transition(
                    connection,
                    task,
                    current,
                    "pending_confirmation",
                    actor,
                    {
                        "channel_message_id": body.candidateId,
                        "resolved_by": actor,
                        "resolved_at": now(),
                        "resolution_reason": body.reason,
                        "error_message": None,
                        "evidence_json": {**current["evidence_json"], "reconciliation": matches[0][2]},
                    },
                )
        except SQLAlchemyError:
            raise ApiError(409, "渠道记录已关联或保存结果待核实，请读取原执行记录") from None
        return view(self.receipts.read(task_id, row["id"]))
