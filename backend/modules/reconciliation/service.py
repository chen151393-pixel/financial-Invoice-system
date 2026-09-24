"""本地财务审核与兼容NS查询：不可变预览、来源复核及事务内确认。"""

import json
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.audit.public import record_finance_review
from backend.modules.business.public import PlScriptQuery

from . import dao, local_mapper, mapper, policy, task_dao
from .task_service import generate_tasks
from .vo import Declaration, ReviewResult


class ReconciliationService:
    def __init__(self, settings, source, engine, local_source=None):
        self.settings, self.source, self.engine = settings, source, engine
        self.local_source = local_source

    def browse(self, body, owner):
        if self.local_source is None:
            raise ApiError(503, "业务数据库未配置")
        try:
            with self.engine.connect() as connection:
                approved = [
                    {**row, "source": json.loads(row["payload"]).get("source", "netsuite")}
                    for row in dao.approved_sources(connection, owner)
                ]
        except SQLAlchemyError:
            raise ApiError(503, "审核状态读取失败，请检查应用数据库及迁移状态") from None
        data = self.local_source.read(
            owner,
            keyword=body.keyword.strip(),
            account=body.account,
            page=body.page,
            page_size=body.pageSize,
            include_rows=True,
            status=body.status,
            approved=approved,
        )
        groups = local_mapper.declarations(data)
        self._local_previews(data, groups, owner, approved)
        total = data["total"]
        return ReviewResult(
            source="database",
            requestId=str(uuid.uuid4()),
            readCompletedAt=datetime.now(UTC).isoformat(),
            groups=groups,
            accounts=data["accounts"],
            page=body.page,
            pageSize=body.pageSize,
            total=total,
            pages=max(1, (total + body.pageSize - 1) // body.pageSize),
            counts={
                **data["counts"],
                "shown": len(groups),
                "customs": sum(group.customsCount for group in groups),
                "purchase": sum(group.purchaseCount for group in groups),
            },
        )

    def _local_previews(self, data, groups, owner, approved):
        """财务审核已入库内容，关联技术诊断不再作为前置审核环节。"""
        reviewed = {(row["account"], row["declaration_id"]): row for row in approved}
        now = int(time.time())
        try:
            with self.engine.begin() as connection:
                for head, group in zip(data["heads"], groups, strict=True):
                    source = data["review_sources"][head["id"]]
                    previous = reviewed.get((group.account, head["ns_internal_id"]))
                    digest = source["digest"]
                    comparison = data.get("relations", {}).get(head["id"], {}).get("comparison")
                    if (
                        previous
                        and previous["source"] != "database"
                        and comparison
                        and previous["digest"] == comparison["digest"]
                    ):
                        digest = previous["digest"]
                    if previous and previous["digest"] == digest:
                        group.review = mapper.review_state(previous, digest, "")
                        continue
                    reason = policy.local_review_reason(
                        self._one_data(data, head["id"]), owner, self.settings.admin_user
                    )
                    group.review.reason = reason
                    if reason:
                        continue
                    current = dao.head(connection, owner, group.account, head["ns_internal_id"])
                    group.snapshotId = str(uuid.uuid4())
                    dao.add_snapshot(
                        connection,
                        {
                            "id": group.snapshotId,
                            "owner": owner,
                            "account": group.account,
                            "declaration_id": head["ns_internal_id"],
                            "digest": source["digest"],
                            "revision": current["revision"],
                            "payload": json.dumps(
                                {
                                    "source": "database",
                                    "version": 1,
                                    "content": source["content"],
                                    "display": group.model_dump(),
                                },
                                ensure_ascii=False,
                            ),
                            "created_at": now,
                            "expires_at": now + 900,
                        },
                    )
                    group.review = mapper.review_state(current, source["digest"], "")
        except SQLAlchemyError:
            raise ApiError(503, "审核预览保存失败，请检查应用数据库") from None

    @staticmethod
    def _one_data(data, head_id):
        purchases = [row for row in data["purchases"] if row["customs_declaration_id"] == head_id]
        purchase_ids = {row["id"] for row in purchases}
        return {
            "heads": [head for head in data["heads"] if head["id"] == head_id],
            "details": [row for row in data["details"] if row["customs_declaration_id"] == head_id],
            "lines": [row for row in data["lines"] if row["purchase_order_id"] in purchase_ids],
        }

    def _approve_local(self, preview, payload, body, owner):
        if self.local_source is None:
            raise ApiError(503, "业务数据库未配置")
        if mapper.digest(payload["content"]) != preview["digest"]:
            raise ApiError(409, "审核快照内容不一致，请重新查询")
        # 与来源同步共用账户锁，直到应用库审核和审计一起提交后才释放。
        with self.local_source.locked_review(owner, preview["account"], preview["declaration_id"]) as data:
            head_id = data["heads"][0]["id"]
            reason = policy.local_review_reason(data, owner, self.settings.admin_user)
            if reason or data["review_sources"][head_id]["digest"] != preview["digest"]:
                raise ApiError(409, reason or "报关单或子采购明细已更新，请重新查询并核对后审核")
            now = int(time.time())
            with self.engine.begin() as connection:
                head = dao.head(connection, owner, preview["account"], preview["declaration_id"])
                if head["digest"] != preview["digest"]:
                    if preview["expires_at"] <= now:
                        raise ApiError(409, "审核预览已过期，请重新查询后核对")
                    if head["revision"] != preview["revision"] or not dao.approve(
                        connection, preview, owner, now, body.note.strip()
                    ):
                        raise ApiError(409, "报关单已被其他请求审核，请重新查询")
                    record_finance_review(
                        connection, at=now, actor=owner, snapshot_id=preview["id"], note=body.note.strip()
                    )
                    generate_tasks(connection, preview, payload, owner, now)
                    head = dao.head(connection, owner, preview["account"], preview["declaration_id"])
                group = Declaration.model_validate(payload["display"])
                group.invoiceTaskCount = task_dao.count_snapshot(connection, owner, head["snapshot_id"])
                group.snapshotId = preview["id"]
                group.review = mapper.review_state(head, preview["digest"], "")
                return group

    def _raw(self, group, result):
        raw = group.model_dump()
        if result.query.type == "pl" and result.query.pl:
            raw["reviewIssues"] = [*raw["reviewIssues"], "请按CD编号查询完整报关单后审核"]
        return raw

    def query(self, body, owner):
        result = self.source.query(body.criteria)
        groups = []
        now = int(time.time())
        try:
            with self.engine.begin() as connection:
                for source_group in result.groups:
                    raw = self._raw(source_group, result)
                    group = mapper.declaration(raw, result.contractVersion)
                    head = dao.head(connection, owner, self.settings.account, group.id)
                    payload = {"version": result.contractVersion, "group": raw}
                    source_digest = mapper.digest(payload)
                    group.snapshotId = str(uuid.uuid4())
                    dao.add_snapshot(
                        connection,
                        {
                            "id": group.snapshotId,
                            "owner": owner,
                            "account": self.settings.account,
                            "declaration_id": group.id,
                            "digest": source_digest,
                            "revision": head["revision"],
                            "payload": json.dumps(payload, ensure_ascii=False),
                            "created_at": now,
                            "expires_at": now + 900,
                        },
                    )
                    reason = policy.blocked_reason(
                        raw, result.contractVersion, owner, self.settings.admin_user
                    )
                    group.review = mapper.review_state(head, source_digest, reason)
                    if head["digest"] and head["digest"] != source_digest:
                        group.warnings.append("来源或查询范围与上次审核不一致，旧审核结果不适用于本次数据。")
                    groups.append(group)
        except SQLAlchemyError:
            raise ApiError(503, "审核数据库不可用，请检查数据库连接并执行应用库迁移") from None
        counts = {
            "all": len(groups),
            **{
                status: sum(group.review.status == status for group in groups)
                for status in ("pending", "approved", "blocked")
            },
        }
        selected = [group for group in groups if body.status == "all" or group.review.status == body.status]
        counts.update(
            customs=sum(group.customsCount for group in selected),
            purchase=sum(group.purchaseCount for group in selected),
            shown=len(selected),
        )
        return ReviewResult(
            requestId=result.requestId,
            readCompletedAt=result.readCompletedAt,
            groups=selected,
            counts=counts,
            notices=["当前NS接口未提供显式行关联，采购明细保留在待关联区，审核暂不可用。"]
            if result.contractVersion != 3
            else [],
        )

    def approve(self, body, owner):
        if owner != f"user:{self.settings.admin_user}":
            raise ApiError(403, "当前身份没有财务审核权限")
        try:
            with self.engine.connect() as connection:
                preview = dao.snapshot(connection, body.snapshotId, owner)
            if preview is None:
                raise ApiError(404, "审核预览不存在或无权访问")
            payload = json.loads(preview["payload"])
            if payload.get("source") == "database":
                return self._approve_local(preview, payload, body, owner)
            if preview["account"] != self.settings.account:
                raise ApiError(404, "审核预览不存在或无权访问")
            raw, version = payload["group"], payload["version"]
            reason = policy.blocked_reason(raw, version, owner, self.settings.admin_user)
            if reason:
                raise ApiError(409, reason)
            with self.engine.begin() as connection:
                head = dao.head(connection, owner, self.settings.account, preview["declaration_id"])
                # 网络中断后重试同一预览，只返回已持久化结果，不重复记账或改变备注。
                if head["snapshot_id"] == preview["id"]:
                    group = mapper.declaration(raw, version)
                    group.invoiceTaskCount = task_dao.count_snapshot(connection, owner, head["snapshot_id"])
                    group.snapshotId = preview["id"]
                    group.review = mapper.review_state(head, preview["digest"], "")
                    return group
            if preview["expires_at"] <= int(time.time()):
                raise ApiError(409, "审核预览已过期，请重新查询后核对")
            # NS网络读取在数据库锁之外；按CD重新读取整单，不接受客户端提交金额或状态。
            fresh = self.source.query(
                PlScriptQuery(type="customsRecord", pl=raw["recordNumber"], showIncomplete=True)
            )
            matches = [group for group in fresh.groups if group.declarationId == raw["declarationId"]]
            if len(matches) != 1:
                raise ApiError(409, "报关单来源范围已变化，请重新查询")
            fresh_raw = self._raw(matches[0], fresh)
            fresh_payload = {"version": fresh.contractVersion, "group": fresh_raw}
            reason = policy.blocked_reason(fresh_raw, fresh.contractVersion, owner, self.settings.admin_user)
            if reason or mapper.digest(fresh_payload) != preview["digest"]:
                raise ApiError(409, "NS明细或关联关系已变化，请重新查询并核对后再审核")
            now = int(time.time())
            with self.engine.begin() as connection:
                head = dao.head(connection, owner, self.settings.account, preview["declaration_id"])
                if head["digest"] != preview["digest"]:
                    if head["revision"] != preview["revision"] or not dao.approve(
                        connection, preview, owner, now, body.note.strip()
                    ):
                        raise ApiError(409, "报关单已被其他请求审核，请重新查询")
                    record_finance_review(
                        connection, at=now, actor=owner, snapshot_id=preview["id"], note=body.note.strip()
                    )
                    generate_tasks(connection, preview, payload, owner, now)
                    head = dao.head(connection, owner, self.settings.account, preview["declaration_id"])
                group = mapper.declaration(raw, version)
                group.invoiceTaskCount = task_dao.count_snapshot(connection, owner, head["snapshot_id"])
                group.snapshotId = preview["id"]
                group.review = mapper.review_state(head, preview["digest"], "")
                return group
        except SQLAlchemyError:
            raise ApiError(
                503, "审核保存结果暂无法确认，请使用同一审核预览重试；系统会核查已有记录，避免重复确认"
            ) from None
