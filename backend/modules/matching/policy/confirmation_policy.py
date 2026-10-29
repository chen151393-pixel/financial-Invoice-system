"""分配视图的操作能力与中文原因；实际提交仍重新校验。"""

from ..vo.matching_vo import Capability
from . import allocation_policy as rules
from .comparison_policy import compare


def evaluate(row, invoice, item, line, task_line, used):
    """返回 (当前比对项, 能力, 需填写说明的原因)。"""
    checks = (row["checks"] or {}).get("items", [])
    capabilities = {
        "confirm": Capability(reason="只有待审核建议可以通过"),
        "reject": Capability(reason="只有待审核建议可以驳回"),
        "cancel": Capability(reason="只有已通过的分配可以取消"),
        "reverify": Capability(reason="无需复核"),
        "replace": Capability(reason="只有已确认占用可以替换"),
    }
    reasons = []
    if row["status"] == "confirmed":
        capabilities["replace"] = Capability(
            allowed=True, reason="取消原占用与新分配同时提交，失败时原占用保持不变"
        )
        capabilities["cancel"] = Capability(allowed=True, reason="取消后任务收票进度按剩余分配重算")
        block = rules.hard_block(invoice, line, task_line)
        capabilities["reverify"] = Capability(
            allowed=row["verification_status"] != "valid" and not block and item["is_active"],
            reason=block or "按当前两端版本重新核实，保留原确认历史",
        )
    if row["status"] != "proposed":
        return checks, capabilities, reasons
    block = rules.hard_block(invoice, line, task_line)
    if not block and line["digest"] != (row["checks"] or {}).get("purchaseDigest"):
        block = "子采购行内容在建议生成后已变化，比对依据过期，请驳回后重新生成建议"
    if not block:
        block = rules.capacity_block(item, *used, row["quantity"], row["amount"])
    if line is not None and task_line is not None:
        compared = {**item, "quantity": row["quantity"], "amount_including_tax": row["amount"]}
        checks, _ = compare(invoice, compared, line, *rules.remaining(task_line))
        exceeds = rules.exceeds_expected(task_line, row["quantity"], row["amount"])
        if (row["checks"] or {}).get("group"):
            # 整单建议按发票行对整单合计比对（详情页实时重算），逐条记录沿用生成时的整单比对项
            checks = row["checks"].get("items", [])
        reasons = rules.note_reasons(checks, exceeds, False)
    capabilities["confirm"] = Capability(
        allowed=not block, reason=block or ("通过时需填写说明" if reasons else "无需填写说明，可直接通过")
    )
    capabilities["reject"] = Capability(allowed=True, reason="驳回后可重新生成建议或人工分配")
    return checks, capabilities, reasons
