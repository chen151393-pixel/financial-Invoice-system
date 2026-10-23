"""业务状态（2026-10-23 业务确认）：由审核与开票任务状态汇总得出，只读，不提供人工修改入口。

| 业务状态 | 开票任务状态 |
| --- | --- |
| 待审批 pending_review | （报关单待审核，由 review 判断；无任务） |
| 待通知开票 notify | 待保存子采购合同、待通知供应商 |
| 待核票 invoicing | 等待开票、部分收票 |
| 资料已回 documents | 发票已收齐、资料待补齐 |
| 开票完成 completed | 发票收齐且资料全部到齐 |

报关单级别取其当前任务中最慢的阶段；审核通过但没有任何任务（供应商均关闭通知）为"无需开票"。
"""

STAGES = ("pending_review", "notify", "invoicing", "documents", "completed")
STAGE_LABELS = {
    "pending_review": "待审批",
    "notify": "待通知开票",
    "invoicing": "待核票",
    "documents": "资料已回",
    "completed": "开票完成",
    "none": "无需开票",
}
TASK_STAGES = {
    "documents_pending": "notify",
    "notify_pending": "notify",
    "awaiting_invoice": "invoicing",
    "partially_received": "invoicing",
    "documents_incomplete": "documents",
    "completed": "completed",
}


def task_stage(status):
    """单个任务的业务状态；已被替代的任务没有业务状态。"""
    return TASK_STAGES.get(status)


def declaration_stage(task_statuses):
    """报关单下当前任务中最慢的业务状态；没有当前任务为 none。"""
    stages = [TASK_STAGES[status] for status in task_statuses if status in TASK_STAGES]
    return min(stages, key=STAGES.index) if stages else "none"
