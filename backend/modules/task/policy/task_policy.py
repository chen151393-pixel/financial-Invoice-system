"""任务状态机、分组键与状态文案（数据库设计第 6 节）。"""

import hashlib
import json
from decimal import Decimal

STATUS_LABELS = {
    "documents_pending": "待保存子采购合同",
    "notify_pending": "待通知供应商",
    "awaiting_invoice": "等待供应商开票",
    "partially_received": "部分收票",
    "completed": "已完成",
    "superseded": "已被新审核版本替代",
}

STATUS_REASONS = {
    "documents_pending": "财务审核已通过，将子采购合同保存到共享盘后通知供应商。",
    "notify_pending": "子采购合同已保存到共享盘，等待通知供应商开票。",
    "awaiting_invoice": "通知已登记或经企微渠道确认，等待供应商开票；具体渠道见通知记录。",
    "partially_received": "已收到部分发票，等待其余发票。",
    "completed": "全部任务行已结束。",
    "superseded": "请查看该报关单最新审核生成的任务。",
}

# 收票进度由有效分配及当前差异结束决定汇总，不提供任意修改状态的接口。
# 取消已通过的分配后按实际收票退回：仍有收票 → partially_received；没有收票 → 收票前的节点。
PRE_INVOICE = ("documents_pending", "notify_pending", "awaiting_invoice")
TRANSITIONS = {
    "documents_pending": {"notify_pending", "partially_received", "completed", "superseded"},
    "notify_pending": {"awaiting_invoice", "partially_received", "completed", "superseded"},
    "awaiting_invoice": {"partially_received", "completed", "superseded"},
    "partially_received": {"completed", "superseded", *PRE_INVOICE},
    "completed": {"partially_received", "superseded", *PRE_INVOICE},
    "superseded": set(),
}

# 依据换版时包括已完成任务在内均建立后继；旧任务与旧行保留为 superseded 历史。
OPEN_STATUSES = ("documents_pending", "notify_pending", "awaiting_invoice", "partially_received")

LINE_STATUS_LABELS = {
    "open": "未收票",
    "partial": "部分收票",
    "received": "已结束",
    "superseded": "已被替代",
}

SUPERSEDED_REASON = "此任务已被新审核版本替代，仅供追溯。"

# 金额容差：每行 0.01 元（数据库设计第 1 节）
AMOUNT_TOLERANCE = Decimal("0.01")


def can_transition(current, target):
    return target in TRANSITIONS.get(current, set())


def group_key(supplier_id, company_id, currency, purchase_order_id):
    """供应商 × 采购公司 × 币种；任一身份缺失时按子采购单隔离，不凭名称跨单合并。"""
    isolated = f"order:{purchase_order_id}"
    parts = [
        f"supplier:{supplier_id}" if supplier_id else isolated,
        f"company:{company_id}" if company_id else isolated,
        f"currency:{currency}" if currency else isolated,
    ]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def missing_identity_reasons(supplier_id, company_id, currency):
    reasons = []
    if not supplier_id:
        reasons.append("缺少供应商身份标识，暂按子采购单隔离，不能仅凭名称合并。")
    if not company_id:
        reasons.append("缺少采购公司身份标识，不能用申报公司代替开票购方。")
    if not currency:
        reasons.append("来源未提供币种，以子采购订单原件为准；不影响资料下载。")
    return reasons


def event_label(from_status, to_status):
    if from_status is None:
        return "财务审核通过，生成开票任务"
    if from_status in ("partially_received", "completed") and to_status in PRE_INVOICE:
        return "收票依据变化，退回收票前节点"
    if from_status == "completed" and to_status == "partially_received":
        return "收票依据变化，退回部分收票"
    return {
        "notify_pending": "子采购合同已全部保存到共享盘",
        "awaiting_invoice": "通知已发送，等待开票",
        "partially_received": "收到部分发票",
        "completed": "任务完成",
        "superseded": "被新审核版本替代",
    }.get(to_status, STATUS_LABELS.get(to_status, to_status))


def line_progress(expected_quantity, expected_amount, received_quantity, received_amount, closed):
    """任务行状态（数据库设计第 6.1 节）：返回 (status, over_invoiced, closed_with_difference)。

    已收齐 = 数量相等且金额相差不超过 0.01 元；超开 = 已收数量或金额超过应开值。
    应开金额为空的行只能由人工按差异结束（closed）。
    """
    full = (
        expected_quantity is not None
        and expected_amount is not None
        and received_quantity == expected_quantity
        and abs(received_amount - expected_amount) <= AMOUNT_TOLERANCE
    )
    over = (expected_quantity is not None and received_quantity > expected_quantity) or (
        expected_amount is not None and received_amount - expected_amount > AMOUNT_TOLERANCE
    )
    if full or closed:
        status = "received"
    elif received_quantity or received_amount:
        status = "partial"
    else:
        status = "open"
    return status, over, bool(closed and not full)


def task_progress(line_statuses, base_status):
    """全部有效任务行已结束 → completed；有收票 → partially_received；否则回到收票前节点 base_status。"""
    if line_statuses and all(status == "received" for status in line_statuses):
        return "completed"
    if any(status in ("partial", "received") for status in line_statuses):
        return "partially_received"
    return base_status
