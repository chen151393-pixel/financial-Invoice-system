"""按组拆为独立事务；组内成员全部成功才提交，不切分为 50 条原任务的小批。"""

from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import supplier_task_dao, task_dao
from ..policy.notification_group_policy import group_revision, member_revision, record_block
from ..vo.notification_vo import NotificationGroupBatchResult, NotificationGroupOutcome
from .board_facts import board_facts
from .notification_batch_service import SAVE_ERROR, _record, validate_batch


def _members(connection, selection, group_by):
    if group_by == "supplier":
        rows = supplier_task_dao.by_anchor(connection, int(selection.id), lock=True)
    else:
        rows = task_dao.by_ids(connection, [int(selection.id)], lock=True)
    if not rows:
        raise ApiError(404, "任务组不存在，请刷新列表")
    facts = board_facts(connection, rows)
    revisions = [(str(row["id"]), member_revision(row, facts[row["id"]])) for row in rows]
    current = group_revision(revisions) if group_by == "supplier" else revisions[0][1]
    if current != selection.scopeRevision:
        raise ApiError(409, "任务组成员、通知或可登记范围已变化，请刷新后重新确认；本组未登记")
    members = [row for row in rows if not record_block(row, facts[row["id"]])]
    if not members:
        raise ApiError(409, "本组没有可登记的待通知任务，请刷新列表")
    return members


def record_groups(engine, body, actor):
    note = validate_batch(body, actor)
    results = []
    # 每组选中项为一个处理批次：大组不拆开，组内失败不会留下部分已登记成员。
    for selection in body.groups:
        task_ids = []
        try:
            with transaction(engine, "task") as connection:
                members = _members(connection, selection, body.groupBy)
                task_ids = [str(row["id"]) for row in members]
                at = datetime.now(UTC).replace(tzinfo=None)
                for row in members:
                    # 复用原登记的来源、未决通知、日期与状态校验；合并通知保护同样保留。
                    _record(connection, row["id"], note, actor, at, body.notifiedOn)
        except ApiError as error:
            status = "skipped" if error.status in (400, 404, 409, 422) else "unknown"
            reason = error.message
        except SQLAlchemyError:
            # 提交结果无法确认时不能声称整组失败，更不能自动重放。
            status, reason = "unknown", SAVE_ERROR
        else:
            status, reason = "recorded", "本组待通知任务已全部登记"
        results.append(
            NotificationGroupOutcome(id=selection.id, status=status, taskIds=task_ids, reason=reason)
        )
    return NotificationGroupBatchResult(
        groups=results,
        recordedGroups=sum(item.status == "recorded" for item in results),
        skippedGroups=sum(item.status == "skipped" for item in results),
        unknownGroups=sum(item.status == "unknown" for item in results),
        recordedTasks=sum(len(item.taskIds) for item in results if item.status == "recorded"),
    )
