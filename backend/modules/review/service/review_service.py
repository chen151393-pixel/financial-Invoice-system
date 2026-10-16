"""财务核对：列表（按审核状态筛选、分页）与整单审核确认。

审核确认在 source 的同步账户锁内、同一事务中完成：重读来源 → 核对摘要 → 写审核记录与冻结行 →
发布 ReviewApproved（订阅方在同一事务中处理）。来源在页面打开后变化时拒绝，要求刷新重核。
"""

from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.source.public import digest as source_digest
from backend.modules.source.public import snapshot as source_snapshot
from backend.modules.source.public import unit_names

from ..dao import purchase_basis_dao, review_line_dao, review_record_dao
from ..mapper import declaration_mapper
from ..policy.review_policy import NO_PURCHASE_REASON, approve_block_reason, status
from ..public import ReviewApproved
from ..vo.review_vo import ReviewList
from .basis_reader import current_bases
from .purchase_basis_service import freeze, same_evidence


class ReviewService:
    def __init__(self, engine, declarations, events):
        self.engine, self.declarations, self.events = engine, declarations, events

    def _actives(self, declaration_ids):
        try:
            with self.engine.connect() as connection:
                found = review_record_dao.active_by_declarations(connection, declaration_ids)
                required = purchase_basis_dao.required_declarations(
                    connection, [r["id"] for r in found.values()]
                )
                for row in found.values():
                    row["basis_required"] = row["id"] in required
                return found
        except SQLAlchemyError:
            raise ApiError(503, "审核记录读取失败，请检查数据库及迁移状态") from None

    def browse(self, query):
        index = self.declarations.index(query.account, query.keyword)
        actives = self._actives([row["id"] for row in index])
        states = {
            row["id"]: ("pending", True)
            if (actives.get(row["id"]) or {}).get("basis_required")
            else status(row["content_sha256"], row["order_count"], actives.get(row["id"]))
            for row in index
        }
        counts = {"all": len(index), "pending": 0, "approved": 0, "blocked": 0}
        for state, _ in states.values():
            counts[state] += 1
        selected = [row["id"] for row in index if query.status in ("all", states[row["id"]][0])]
        start = (query.page - 1) * query.pageSize
        page_ids = selected[start : start + query.pageSize]
        groups = [
            self._declaration(content, states[content["declaration"]["id"]], actives)
            for content in self.declarations.details(page_ids)
            if content is not None
        ]
        counts.update(
            customs=sum(group.customsCount for group in groups),
            purchase=sum(group.purchaseCount for group in groups),
            shown=len(groups),
        )
        return ReviewList(
            groups=groups,
            counts=counts,
            accounts=self.declarations.accounts(),
            page=query.page,
            pageSize=query.pageSize,
            total=len(selected),
            pages=max(1, (len(selected) + query.pageSize - 1) // query.pageSize),
        )

    def _declaration(self, content, state_changed, actives):
        try:
            with self.engine.connect() as connection:
                content = {
                    **content,
                    "bases": current_bases(connection, [r["id"] for r in content["purchase_lines"]]),
                    "unit_names": unit_names(connection),
                }
        except SQLAlchemyError:
            raise ApiError(503, "审核依据读取失败，请检查数据库及迁移状态") from None
        state, changed = state_changed
        active = actives.get(content["declaration"]["id"])
        reason = NO_PURCHASE_REASON if state == "blocked" else ""
        return declaration_mapper.declaration(content, state, changed, active, state == "pending", reason)

    def approve(self, declaration_id, body, actor):
        if actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能进行财务审核")
        head = self.declarations.detail(declaration_id)["declaration"]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            with self.declarations.locked(head["ns_account"]) as connection:
                self._approve_in(connection, declaration_id, body, actor, now)
        except SQLAlchemyError:
            raise ApiError(503, "审核结果暂无法确认，请刷新后查看；同一内容重复提交不会重复审核") from None
        return self._current(declaration_id)

    def _approve_in(self, connection, declaration_id, body, actor, now):
        content = source_snapshot(connection, declaration_id)
        if content is None:
            raise ApiError(404, "报关单不存在")
        current = source_digest(content)
        stored = content["declaration"]["content_sha256"]
        active = review_record_dao.active(connection, declaration_id, lock=True)
        basis_required = (
            bool(purchase_basis_dao.required_declarations(connection, [active["id"]])) if active else False
        )
        if (
            active
            and same_evidence(connection, declaration_mapper.review_lines(content), body)
            and active["content_sha256"] == body.contentSha256 == current
        ):
            return  # 同一内容已审核：重复提交只返回已有结果
        state, _ = status(current, len(content["orders"]), active)
        if basis_required or body.currencyEvidence:
            state = "pending"
        reason = approve_block_reason(state, current if stored == current else None, body.contentSha256)
        if reason:
            raise ApiError(409, reason)
        if active:
            review_record_dao.supersede(connection, active["id"], now)
        head = content["declaration"]
        revision = review_record_dao.max_revision(connection, declaration_id) + 1
        review_id = review_record_dao.insert_record(
            connection,
            {
                "ns_account": head["ns_account"],
                "customs_declaration_id": declaration_id,
                "record_no": head["record_no"],
                "revision": revision,
                "content_sha256": current,
                "approved_by": actor,
                "approved_at": now,
                "note": body.note.strip() or None,
            },
            now,
        )
        rows = freeze(
            connection, content, declaration_mapper.review_lines(content), body, review_id, actor, now
        )
        ids = review_line_dao.insert_lines(connection, review_id, rows, now)
        self.events.publish(
            connection,
            ReviewApproved(
                review_id=review_id,
                superseded_review_id=active["id"] if active else None,
                ns_account=head["ns_account"],
                customs_declaration_id=declaration_id,
                record_no=head["record_no"],
                revision=revision,
                approved_by=actor,
                lines=declaration_mapper.approved_lines(rows, ids),
            ),
        )

    def _current(self, declaration_id):
        content = self.declarations.detail(declaration_id)
        actives = self._actives([declaration_id])
        state = status(
            content["declaration"]["content_sha256"], len(content["orders"]), actives.get(declaration_id)
        )
        if (actives.get(declaration_id) or {}).get("basis_required"):
            state = ("pending", True)
        return self._declaration(content, state, actives)
