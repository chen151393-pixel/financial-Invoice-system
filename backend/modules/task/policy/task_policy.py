"""任务状态机、分组键与状态文案（数据库设计第 6 节）。"""

import hashlib
import json

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
    "awaiting_invoice": "已人工登记发送通知，等待供应商开票；尚无企微渠道回执。",
    "partially_received": "已收到部分发票，等待其余发票。",
    "completed": "全部任务行已结束。",
    "superseded": "请查看该报关单最新审核生成的任务。",
}

# 收票进度（partially_received、completed）由发票比对的分配汇总得出，第 4d 步接入，不提供手动修改。
TRANSITIONS = {
    "documents_pending": {"notify_pending", "partially_received", "completed", "superseded"},
    "notify_pending": {"awaiting_invoice", "partially_received", "completed", "superseded"},
    "awaiting_invoice": {"partially_received", "completed", "superseded"},
    "partially_received": {"completed", "superseded"},
    "completed": set(),
    "superseded": set(),
}

# 新审核替代旧审核时，未完成的任务改为 superseded；已完成的任务保留，其任务行仍有效。
OPEN_STATUSES = ("documents_pending", "notify_pending", "awaiting_invoice", "partially_received")

LINE_STATUS_LABELS = {
    "open": "未收票",
    "partial": "部分收票",
    "received": "已结束",
    "superseded": "已被替代",
}

SUPERSEDED_REASON = "此任务已被新审核版本替代，仅供追溯。"


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
    return {
        "notify_pending": "子采购合同已全部保存到共享盘",
        "awaiting_invoice": "人工登记已发送通知",
        "partially_received": "收到部分发票",
        "completed": "任务完成",
        "superseded": "被新审核版本替代",
    }.get(to_status, STATUS_LABELS.get(to_status, to_status))
