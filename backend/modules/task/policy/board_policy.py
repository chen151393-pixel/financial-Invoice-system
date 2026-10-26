"""采购开票任务台的节点文案与下一步提示，纯函数。

节点是否完成沿用详情页六个节点的判定（task_mapper.steps）；任务台按"当前节点"（第一个未完成的节点）归类。
财务审核节点对已生成的任务总是完成，不作为任务台分区；已完成任务归入 done。
"""

# 任务台分区：按当前节点表达"在等什么"，顺序与流程一致
NODES = ("documents", "notification", "invoices", "comparison", "completion", "done")
NODE_LABELS = {
    "documents": "待存合同",
    "notification": "待通知供应商",
    "invoices": "待供应商开票",
    "comparison": "部分收票",
    "completion": "待补资料",
    "done": "已完成",
}
NODE_HINTS = {
    "documents": "子采购合同尚未全部保存到共享盘",
    "notification": "合同已就绪，尚未通知供应商开票",
    "invoices": "已通知，尚未收到发票",
    "comparison": "已收到部分发票，仍有任务行未结束",
    "completion": "发票已收齐，资料尚未到齐",
    "done": "发票收齐且资料全部归档",
}
NEXT_ACTIONS = {
    "documents": "系统自动从 NS 下载子采购合同；下载失败时进入跟进详情重试。",
    "notification": "通知供应商开票：在跟进详情中企微群发，或线下发送后登记。",
    "invoices": "跟进供应商开票；发票比对通过后自动更新收票进度。",
    "comparison": "跟进剩余发票；财务在发票比对页审核后自动更新。",
    "done": "任务已完结，无需处理。",
}


def next_action(node, missing):
    if node != "completion":
        return NEXT_ACTIONS[node]
    text = f"补齐资料：{'、'.join(missing)}。" if missing else "资料到齐后自动完结。"
    if "回签合同" in missing:
        text += "回签合同可在开票跟进页批量上传。"
    return text


def current_node(steps):
    """第一个处于当前状态的节点；已完成或没有当前节点的任务归入 done。"""
    return next((step.key for step in steps if step.state == "current"), "done")
