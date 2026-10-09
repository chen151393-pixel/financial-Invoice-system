"""回写用例：校验、不可变预览、执行权、事务与结果恢复。"""

import json
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from backend.core.errors import ApiError
from backend.modules.audit.public import record

from . import dao
from .mapper import to_preview
from .policy import WritebackPolicy, encode, fingerprint, millis


class WritebackService:
    def __init__(self, settings, ns, engine):
        self.settings, self.ns, self.engine = settings, ns, engine
        self.policy = WritebackPolicy(settings, ns)

    def validate(self, body):
        self.policy.validate(body)

    def audit(self, connection, actor, action, preview_id):
        record(connection, at=millis(), actor=actor, action=action, preview_id=preview_id)

    def get(self, preview_id, owner):
        with self.engine.connect() as connection:
            row = dao.get(connection, preview_id, owner, self.settings.account)
        if row is None:
            raise ApiError(404, "预览或任务不存在")
        return to_preview(row)

    def list_jobs(self, owner):
        with self.engine.connect() as connection:
            return [dict(row) for row in dao.list_jobs(connection, owner, self.settings.account)]

    def describe(self, preview_id, owner):
        result = self.get(preview_id, owner)
        reason = None
        if result["state"] != "preview":
            reason = "任务已执行或结果待核实，请刷新状态"
        elif not self.settings.write_enabled:
            reason = "服务器尚未启用实际写入"
        elif result["expires"] <= millis():
            reason = "预览已过期，请重新生成"
        result["actions"] = {"execute": {"allowed": reason is None, "reason": reason}}
        result["stateLabel"] = {
            "preview": "待确认",
            "executing": "执行中",
            "succeeded": "已成功",
            "unknown": "结果待核实",
        }.get(result["state"], result["state"])
        return result

    def preview_text(self, body, owner):
        try:
            payload = json.loads(body["payloadText"])
        except (ValueError, RecursionError):
            raise ApiError(400, "拟写入字段不是有效JSON，请检查后重新提交") from None
        return self.preview(
            {"operation": body["operation"], "type": body["type"], "id": body.get("id"), "payload": payload},
            owner,
        )

    def execute_confirmed(self, preview_id, confirm, owner):
        if confirm is not True:
            raise ApiError(400, "必须明确确认预览后才能写入")
        return self.execute(preview_id, owner)

    def require_absent(self, record_type, record_id):
        try:
            self.ns.request("GET", record_type, record_id)
        except ApiError as error:
            if error.status == 404:
                return
            raise
        raise ApiError(409, "该 externalId 已存在，不能重复创建")

    def preview(self, body, owner):
        self.validate(body)
        operation, record_type, payload = body["operation"], body["type"], body["payload"]
        before = None
        if operation == "update":
            record_id = str(int(body["id"]))
            before = self.ns.request("GET", record_type, record_id)["data"]
            if not isinstance(before, dict) or str(before.get("id")) != record_id:
                raise ApiError(502, "NS 返回的记录 ID 不匹配，不能生成预览")
        else:
            record_id = f"eid:{payload['externalId']}"
            self.require_absent(record_type, record_id)
        preview_id = str(uuid4())
        with self.engine.begin() as connection:
            dao.create(
                connection,
                {
                    "id": preview_id,
                    "account": self.settings.account,
                    "owner": owner,
                    "target": f"{record_type}/{record_id}",
                    "operation": operation,
                    "payload": encode(payload),
                    "snapshot": encode(before) if before is not None else None,
                    "created_at": millis(),
                    "expires": millis() + 15 * 60000,
                    "state": "preview",
                },
            )
            self.audit(connection, owner, "preview", preview_id)
        return self.get(preview_id, owner)

    def claim(self, preview, owner):
        try:
            with self.engine.begin() as connection:
                if not dao.claim(connection, preview["id"], owner, self.settings.account, millis()):
                    return False
                dao.lock_target(connection, self.settings.account, preview["target"], preview["id"])
                self.audit(connection, owner, "claimed", preview["id"])
                return True
        except IntegrityError:
            raise ApiError(409, "该记录有执行中或结果未知的任务，须先核对") from None

    def transition(self, preview_id, owner, state, result=None, release=False):
        with self.engine.begin() as connection:
            changed = dao.transition(
                connection,
                preview_id,
                owner,
                self.settings.account,
                state,
                encode(result) if result is not None else None,
            )
            if not changed:
                raise ApiError(409, "执行状态已变化，请人工核对 NS")
            if release:
                dao.release_target(connection, preview_id)
            self.audit(connection, owner, state, preview_id)

    def execute(self, preview_id, owner):
        p = self.get(preview_id, owner)
        if p["state"] != "preview":
            return p
        if not self.settings.write_enabled:
            raise ApiError(403, "NS 实际写入尚未启用")
        if p["expires"] <= millis():
            raise ApiError(409, "预览已过期，请重新拉取校对")
        record_type, record_id = p["target"].split("/", 1)
        self.validate(
            {"operation": p["operation"], "type": record_type, "id": record_id, "payload": p["payload"]}
        )
        if not self.claim(p, owner):
            return self.get(preview_id, owner)
        # 远程检查前已取得持久目标锁，HTTP在事务之外执行。
        try:
            token = self.ns.token()
            if p["operation"] == "update":
                current = self.ns.request("GET", record_type, record_id)["data"]
                if fingerprint(current) != fingerprint(p["before"]):
                    raise ApiError(409, "NS 记录已变化，请重新拉取校对")
            else:
                self.require_absent(record_type, record_id)
        except Exception:
            self.transition(preview_id, owner, "preview", release=True)
            raise
        # 请求发出后，传输错误或结果落库失败都不能触发再次写入。
        try:
            result = self.ns.request(
                "POST" if p["operation"] == "create" else "PATCH",
                record_type,
                None if p["operation"] == "create" else record_id,
                p["payload"],
                token,
            )
        except Exception:  # noqa: BLE001 -- 发出写入后任何异常都必须阻止盲目重试。
            self.transition(
                preview_id,
                owner,
                "unknown",
                {"message": "NS 写入未能确认，请人工核对 NS；本任务和该目标均禁止自动重试"},
            )
        else:
            self.transition(preview_id, owner, "succeeded", result, release=True)
        return self.get(preview_id, owner)

    def recover_interrupted(self):
        """仅供所有服务停止后的离线恢复，正常启动不调用。"""
        with self.engine.begin() as connection:
            rows = dao.executing(connection, self.settings.account)
            for preview_id, owner in rows:
                dao.transition(
                    connection,
                    preview_id,
                    owner,
                    self.settings.account,
                    "unknown",
                    encode({"message": "服务中断，必须人工核对 NS，禁止自动重试"}),
                )
                self.audit(connection, owner, "recovered_unknown", preview_id)
        return len(rows)
