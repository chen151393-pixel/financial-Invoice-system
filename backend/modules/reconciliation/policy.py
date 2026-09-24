"""整单人工审核条件；兼容NS实时查询另保留来源完整性校验。"""

from backend.modules.business.public import incomplete_relation_reason


def blocked_reason(raw, version, owner, admin):
    if owner != f"user:{admin}":
        return "当前身份没有财务审核权限"
    return incomplete_relation_reason(raw, version)


def local_review_reason(data, owner, admin):
    if owner != f"user:{admin}":
        return "当前身份没有财务审核权限"
    if len(data["heads"]) != 1 or not data["heads"][0]["ns_internal_id"]:
        return "报关单来源身份不完整，请重新同步"
    if not data["details"]:
        return "暂无报关明细，请先同步报关单"
    if not data["lines"]:
        return "暂无关联子采购明细，请先同步子采购单"
    return ""
