"""企微通知预览与一次性提交；外部读取、上传、创建均不占数据库事务。"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.integrations.wecom_messaging import WeComRejected

from ..dao import notification_delivery_dao as dao
from ..dao import notification_group_guard_dao as guards
from ..dao import task_dao
from ..mapper.delivery_mapper import view
from ..policy.delivery_policy import ACTIVE, submit_reason
from ..vo.capability import Capability
from ..vo.delivery_vo import DeliveryPreview
from .basis_guard import reason as basis_reason
from .basis_guard import require_current
from .delivery_snapshot import digest, evidence_warning, load, read_files, snapshot
from .delivery_state import event, now, require_writer, transition


class DeliverySubmitService:
    def __init__(self, engine, settings, channel, tasks):
        self.engine, self.settings, self.channel, self.tasks = engine, settings, channel, tasks

    def _validate(self, connection, data, body, exclude=None):
        active = [
            row for row in dao.overlapping(connection, data["task"]["id"], ACTIVE) if row["id"] != exclude
        ]
        reason = submit_reason(
            data["task"],
            data["latest"],
            data["binding"],
            self.settings,
            bool(active),
            basis_reason(connection, data["task"]["id"]),
        )
        if reason:
            raise ApiError(409, reason)
        if data["latest"]["version"] != body.revision or data["binding"]["version"] != body.groupRevision:
            raise ApiError(409, "通知或群绑定已变化，请重新预览")
        if len(data["latest"]["content"].encode("utf-8")) > 4000:
            raise ApiError(400, "企微通知正文不能超过 4000 字节，请缩短后保存")
        previous = dao.history(connection, data["task"]["id"])
        if any(row["notification_id"] == data["latest"]["id"] and row["id"] != exclude for row in previous):
            raise ApiError(409, "该通知版本已有执行记录；明确失败后请先保存新版本")

    def _prepare(self, task_id, body):
        with self.engine.connect() as connection:
            data = load(connection, task_id)
            self._validate(connection, data, body)
        corp = self.channel.corp_id()
        if corp != self.settings.wecom_verified_corp_id:
            raise ApiError(409, "当前企微企业与已完成定向验收的企业不一致")
        group = self.channel.group(corp, data["binding"]["chat_id"])
        if group["userid"] != data["binding"]["owner_userid"]:
            raise ApiError(409, "实际群主与供应商绑定不一致，请重新维护供应商群")
        files, contents = read_files(data, self.settings.subpo_archive_root)
        frozen = snapshot(data, corp, group, files)
        return frozen, contents, group

    def preview(self, task_id, body, actor):
        require_writer(actor)
        frozen, _, _ = self._prepare(task_id, body)
        detail = self.tasks.detail(task_id)
        return DeliveryPreview(
            revision=body.revision,
            groupRevision=body.groupRevision,
            snapshotSha256=digest(frozen),
            supplier=detail.task.supplier,
            company=detail.task.company,
            orderNumbers=detail.task.orderNumbers,
            corpId=frozen["corpId"],
            chatId=frozen["chatId"],
            groupName=frozen["groupName"],
            employee=frozen["employee"],
            userid=frozen["userid"],
            message=frozen["message"],
            files=frozen["files"],
            submit=Capability(allowed=True, reason="提交后仍需群主在企微确认发送"),
        )

    def _replay(self, connection, task_id, body):
        row = dao.by_request(connection, body.requestId)
        if row:
            if row["task_id"] != task_id or row["request_sha256"] != digest(body.model_dump()):
                raise ApiError(409, "请求编号已使用，且与当前提交不一致")
            return row
        return None

    def submit(self, task_id, body, actor):
        require_writer(actor)
        with self.engine.connect() as connection:
            prior = self._replay(connection, task_id, body)
        if prior:
            return view(prior)
        frozen, contents, group = self._prepare(task_id, body)
        if digest(frozen) != body.snapshotSha256:
            raise ApiError(409, "预览已过期，通知、群主或合同发生变化，请重新预览")
        try:
            row, claimed = self._claim(task_id, body, actor, frozen, group)
            if claimed:
                self._execute(task_id, body, actor, row, contents)
            with self.engine.connect() as connection:
                return view(dao.get(connection, row["id"]))
        except SQLAlchemyError:
            # 提交事务结果不明时不调用创建；创建后的落库失败保留 submitting 和持久占用。
            raise ApiError(409, "发送记录保存结果待核实，请读取原执行记录，勿重新提交") from None

    def _claim(self, task_id, body, actor, frozen, group):
        with transaction(self.engine) as connection:
            prior = self._replay(connection, task_id, body)
            if prior:
                return prior, False
            require_current(connection, task_id)
            task = task_dao.get(connection, task_id, lock=True)
            data = load(connection, task_id, lock_binding=True)
            self._validate(connection, data, body)
            if digest(snapshot(data, frozen["corpId"], group, frozen["files"])) != body.snapshotSha256:
                raise ApiError(409, "预览数据已变化，请重新预览")
            at = now()
            guard = guards.ensure(connection, frozen["corpId"], frozen["chatId"], at)
            if guard["active_delivery_id"]:
                raise ApiError(409, "该客户群有未决发送任务，请先核实原记录")
            start = (at + timedelta(hours=8)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                hours=8
            )
            count = dao.count_group(
                connection,
                frozen["corpId"],
                frozen["chatId"],
                start,
                start + timedelta(days=1),
                (*ACTIVE, "sent"),
            )
            if count >= self.settings.wecom_group_daily_limit:
                raise ApiError(409, "该群已达到本系统北京时间当日提交上限")
            return self._register_delivery(connection, task, body, actor, frozen, at), True

    @staticmethod
    def _register_delivery(connection, task, body, actor, frozen, at):
        delivery_id = dao.insert_delivery(
            connection,
            {
                "task_id": task["id"],
                "notification_id": frozen["notificationId"],
                "request_id": body.requestId,
                "request_sha256": digest(body.model_dump()),
                "corp_id": frozen["corpId"],
                "chat_id": frozen["chatId"],
                "sender_userid": frozen["userid"],
                "group_binding_id": frozen["bindingId"],
                "group_binding_version": frozen["groupRevision"],
                "snapshot_json": frozen,
                "snapshot_sha256": body.snapshotSha256,
                "status": "preparing",
                "created_by": actor,
                "evidence_json": {},
                "lease_token": uuid4().hex,
                "lease_expires_at": at + timedelta(minutes=15),
            },
            at,
        )
        guards.occupy(connection, frozen["corpId"], frozen["chatId"], delivery_id, at)
        event(connection, task, delivery_id, "preparing", actor, at)
        return dao.get(connection, delivery_id)

    def _before_create(self, task_id, body, row, media_ids, group, actor):
        with transaction(self.engine) as connection:
            require_current(connection, task_id)
            task = task_dao.get(connection, task_id, lock=True)
            current = dao.get(connection, row["id"], lock=True)
            if (
                current["status"] != "preparing"
                or current["lease_token"] != row["lease_token"]
                or current["lease_expires_at"] <= now()
            ):
                raise ApiError(409, "本次执行租约已失效，请刷新核实")
            data = load(connection, task_id, lock_binding=True)
            self._validate(connection, data, body, exclude=row["id"])
            frozen = snapshot(data, row["corp_id"], group, row["snapshot_json"]["files"])
            if digest(frozen) != row["snapshot_sha256"]:
                raise ApiError(409, "上传期间通知、依据或群主变化，未创建群发")
            transition(
                connection,
                task,
                current,
                "submitting",
                actor,
                {"submitted_at": now(), "evidence_json": {"mediaIds": media_ids}},
            )

    def _finish(self, task_id, row, status, actor, values):
        with transaction(self.engine) as connection:
            task = task_dao.get(connection, task_id, lock=True)
            current = dao.get(connection, row["id"], lock=True)
            # 恢复入口可将过期 preparing 关闭；旧执行者不得继续。
            if current["status"] == "failed":
                return
            if current["status"] == "unknown" and status == "unknown":
                return
            if status == "pending_confirmation":
                values = {**values, "error_message": evidence_warning(connection, current) or None}
            transition(connection, task, current, status, actor, values)

    def _execute(self, task_id, body, actor, row, contents):
        frozen = row["snapshot_json"]
        try:
            media_ids = [
                self.channel.upload(row["corp_id"], file["filename"], content)
                for file, content in zip(frozen["files"], contents, strict=True)
            ]
            group = self.channel.group(row["corp_id"], row["chat_id"])
            self._before_create(task_id, body, row, media_ids, group, actor)
        except ApiError as error:
            self._finish(task_id, row, "failed", actor, {"error_message": error.message[:500]})
            return
        try:
            msgid = self.channel.create(
                row["corp_id"], row["chat_id"], row["sender_userid"], frozen["message"], media_ids
            )
        except WeComRejected as error:
            self._finish(
                task_id,
                row,
                "failed",
                actor,
                {"error_code": error.code, "error_message": error.message, "channel_message_id": error.msgid},
            )
        except ApiError:
            self._finish(
                task_id,
                row,
                "unknown",
                actor,
                {"error_message": "创建结果不确定，请核实渠道记录；禁止重复提交"},
            )
        else:
            self._finish(task_id, row, "pending_confirmation", actor, {"channel_message_id": msgid})
