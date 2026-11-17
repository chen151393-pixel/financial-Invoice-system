"""在列表的同一个读取事务中汇总当前双审与实际开票任务。"""

from collections import defaultdict

from backend.modules.source.public import declaration_refs_by_number

from ..dao import (
    customs_approval_dao,
    customs_receipt_dao,
    declaration_snapshot_dao,
    purchase_basis_dao,
    review_line_dao,
    review_record_dao,
)
from ..vo.approval_progress_vo import ApprovalProgress, ApprovalStatus
from ..vo.review_vo import ReviewState


def read_progress(connection, targets, task_reader=None, *, finance_views=None):
    """targets 的键为返回行 ID，值为（真实报关单号，已知 NS 本地 ID）；海关回执可只提供单号。"""
    if not targets:
        return {}
    numbers = sorted({number for number, _ in targets.values() if number})
    refs = declaration_refs_by_number(connection, numbers)
    receipts = customs_receipt_dao.heads_by_numbers(connection, numbers)
    history = defaultdict(list)
    for row in customs_approval_dao.for_receipts(connection, [row["id"] for row in receipts.values()]):
        history[row["receipt_id"]].append(row)

    ids = {row["id"] for matches in refs.values() for row in matches}
    reviews = review_record_dao.active_by_declarations(connection, ids)
    required = purchase_basis_dao.required_declarations(connection, [row["id"] for row in reviews.values()])
    if finance_views is None:
        finance_views = {
            declaration_id: ReviewState.model_validate_json(payload)
            for declaration_id, payload in declaration_snapshot_dao.approval_payloads(connection, ids).items()
        }
    released = {row["id"] for row in reviews.values() if row["customs_approval_id"] is not None}
    tasks = task_reader(connection, review_line_dao.by_reviews(connection, released)) if task_reader else None
    result = {}
    for key, (number, known_id) in targets.items():
        matches = refs.get(number, [])
        source = next((row for row in matches if row["id"] == known_id), None) if known_id else None
        if known_id is None and len(matches) == 1:
            source = matches[0]
        declaration_id = source["id"] if source else None
        digest = source["content_sha256"] if source else None
        active = reviews.get(declaration_id)
        finance = _finance(digest, active, required, finance_views.get(declaration_id))
        receipt = receipts.get(number)
        customs = _customs(number, matches, digest, receipt, declaration_id, history)
        result[key] = _progress(finance, customs, receipt, active, tasks)
        result[key].linked = bool(receipt and declaration_id and len(matches) == 1)
    return result


def _finance(digest, active, required, view):
    if active and digest and active["content_sha256"] == digest and active["id"] not in required:
        return ApprovalStatus(status="approved", label="已通过")
    if active and digest:
        reason = "开票依据或币种待复核" if active["id"] in required else "报关来源已变更，请重新审核"
        return ApprovalStatus(status="changed", label="需重审", reason=reason)
    if not digest:
        return ApprovalStatus(status="blocked", label="待核实", reason="NS 报关单或当前来源摘要尚未就绪")
    return ApprovalStatus(status="pending", label="待审核", reason=view.reason if view else "")


def _customs(number, matches, digest, receipt, declaration_id, history):
    if not number:
        return ApprovalStatus(status="blocked", label="待匹配", reason="NS 尚未提供真实报关单号")
    if len(matches) != 1 or not declaration_id:
        reason = (
            "NS 存在多张同号报关单，请核实后再审核"
            if matches
            else "未找到对应的 NS 报关单，请核对单号或同步 NS"
        )
        return ApprovalStatus(status="blocked", label="待匹配", reason=reason)
    if not receipt:
        return ApprovalStatus(status="pending", label="未导入回执", reason="请先导入对应报关单的海关回执")
    if not digest:
        return ApprovalStatus(status="blocked", label="待核实", reason="NS 来源摘要尚未就绪")
    previous = history.get(receipt["id"], [])
    if any(
        row["receipt_revision"] == receipt["revision"]
        and row["receipt_sha256"] == receipt["content_sha256"]
        and row["customs_declaration_id"] == declaration_id
        and row["source_sha256"] == digest
        for row in previous
    ):
        return ApprovalStatus(status="approved", label="已通过")
    if previous:
        return ApprovalStatus(status="changed", label="需重审", reason="海关回执或 NS 来源已变更，请重新审核")
    return ApprovalStatus(status="pending", label="待审核")


def _progress(finance, customs, receipt, active, tasks):
    def progress(status, label, next_step, reason="", ids=()):
        return ApprovalProgress(
            finance=finance,
            customs=customs,
            status=status,
            label=label,
            reason=reason,
            nextStep=next_step,
            taskIds=[str(task_id) for task_id in sorted(ids)],
        )

    if customs.status == "blocked":
        return progress("blocked", "开票待核实", "details", customs.reason)
    if not receipt:
        return progress("missing_receipt", "等待海关回执", "import", customs.reason)
    if customs.status != "approved" and finance.status != "approved":
        step = "both" if finance.status != "blocked" else "details"
        return progress("waiting_both", "待双审", step, customs.reason or finance.reason)
    if customs.status != "approved":
        return progress("waiting_customs", "等待海关审核", "customs", customs.reason)
    if finance.status != "approved":
        return progress("waiting_finance", "等待财务审核", "finance", finance.reason)
    if active["customs_approval_id"] is None:
        return progress("blocked", "尚未放行", "details", "两项审核已通过，当前审核版本暂无放行记录")
    if tasks is None:
        return progress("released", "已放行", "details", "暂未提供任务查询结果")
    outcome = tasks.get(active["id"])
    if not outcome:
        return progress("no_task", "未生成任务", "details", "当前审核版本没有可用于生成任务的冻结子采购行")
    created, reused = outcome["created"], outcome["reused"]
    reasons = []
    if outcome["muted"]:
        reasons.append(f"{outcome['muted']} 条未关联任务的子采购明细所属供应商当前已关闭通知")
    if outcome["missing"]:
        reasons.append(f"{outcome['missing']} 条子采购明细暂无对应的有效任务")
    reason = "。".join(reasons)
    if created:
        return progress("created", "已生成任务", "tasks", reason, created | reused)
    if reused:
        return progress("reused", "沿用已有任务", "tasks", reason, reused)
    return progress("no_task", "未生成任务", "details", reason)
