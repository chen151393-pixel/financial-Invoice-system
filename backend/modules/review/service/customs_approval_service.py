"""海关审核：当前来源重比对、不可变版本校验、逐张事务与双审核放行。"""

import hashlib
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError
from backend.modules.source.public import declarations_by_number, digest, snapshot

from ..dao import customs_approval_dao, customs_receipt_dao
from ..policy.customs_match_policy import compare
from ..vo.customs_receipt_vo import CustomsApproval, CustomsApproveOutcome, CustomsApproveResult
from .task_release_service import release_if_ready


def approval_view(connection, head, rows):
    """列表与提交共用当前 NS 比对，过期的历史比对结论不能作为准入条件。"""
    candidates = declarations_by_number(connection, [head["declaration_no"]])
    status, declaration_id, result = compare(candidates.get(head["declaration_no"], []), rows)
    content = snapshot(connection, declaration_id) if declaration_id else None
    source_sha = digest(content) if content else ""
    token = hashlib.sha256(
        f"{head['id']}:{head['revision']}:{head['content_sha256']}:{declaration_id}:{source_sha}:{status}".encode()
    ).hexdigest()
    active = customs_approval_dao.current(connection, head, declaration_id, source_sha) if content else None
    stable = bool(content and content["declaration"]["content_sha256"] == source_sha)
    allowed = bool(stable and not active)
    reason = ""
    if active:
        reason = "当前版本已审核通过"
    elif not content:
        reason = "须先唯一匹配到 NS 报关单"
    elif not stable:
        reason = "NS 来源摘要尚未就绪，请重新同步后核对"
    view = CustomsApproval(
        token=token,
        approved=bool(active),
        allowed=allowed,
        autoAllowed=allowed and status in {"matched", "split_matched"},
        label=("自动审核通过" if active["method"] == "auto" else "人工审核通过") if active else "待审核",
        reason=reason,
        approvedBy=active["approved_by"] if active else "",
        approvedAt=active["approved_at"].replace(tzinfo=UTC).isoformat() if active else "",
        note=(active["note"] or "") if active else "",
    )
    return view, declaration_id, source_sha, status, result


class CustomsApprovalService:
    def __init__(self, engine, events):
        self.engine, self.events = engine, events

    def approve_batch(self, body, owner):
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能进行海关审核")
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        approved, skipped = [], []
        for item in body.items:
            try:
                number = self._commit(item, body, owner)
                approved.append(CustomsApproveOutcome(id=item.id, declarationNo=number))
            except ApiError as error:
                if error.status not in (404, 409, 422):
                    raise
                skipped.append(CustomsApproveOutcome(id=item.id, reason=error.message))
        return CustomsApproveResult(approved=approved, skipped=skipped)

    def _commit(self, item, body, owner):
        try:
            # 来源同步、财务审核和海关审核共用账本锁；与导入/换版串行。
            with write_lock.transaction(self.engine) as connection:
                head = customs_receipt_dao.head(connection, item.id, lock=True)
                if not head:
                    raise ApiError(404, "海关回执不存在")
                rows = customs_receipt_dao.current_lines(connection, [head["id"]])[head["id"]]
                view, declaration_id, source_sha, status, result = approval_view(connection, head, rows)
                if view.token != item.token:
                    raise ApiError(409, "回执或 NS 来源已变化，请刷新后重新核对")
                if not view.approved:
                    if not view.allowed:
                        raise ApiError(409, view.reason)
                    if body.method == "auto" and not view.autoAllowed:
                        raise ApiError(409, "仅明细一致（含拆行、合并一致）的回执可自动审核")
                    if status == "different" and not body.note.strip():
                        raise ApiError(422, "有差异的回执须填写人工审核说明")
                    now = datetime.now(UTC).replace(tzinfo=None)
                    customs_approval_dao.approve(
                        connection,
                        {
                            "receipt_id": head["id"],
                            "receipt_revision": head["revision"],
                            "receipt_sha256": head["content_sha256"],
                            "customs_declaration_id": declaration_id,
                            "source_sha256": source_sha,
                            "method": body.method,
                            "approved_by": owner,
                            "note": body.note.strip() or None,
                        },
                        now,
                    )
                    customs_receipt_dao.update_head(
                        connection,
                        head["id"],
                        {
                            "ns_declaration_id": declaration_id,
                            "match_status": status,
                            "match_result": result,
                            "matched_at": now,
                        },
                        now,
                    )
                release_if_ready(connection, declaration_id, self.events)
                return head["declaration_no"]
        except SQLAlchemyError:
            raise ApiError(503, "海关审核结果暂无法确认，部分单据可能已通过，请刷新核实后再操作") from None
