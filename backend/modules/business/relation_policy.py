"""NS关联结果的业务完整性；同步与审核共用，不包含操作者权限。"""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from backend.core.errors import ApiError

from .pl_script_vo import ScriptGroup


def source_digest(payload):
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def number(value, *, positive=False):
    if not isinstance(value, str) or not re.fullmatch(r"-?\d{1,30}(?:\.\d{1,18})?", value):
        return False
    try:
        return Decimal(value) > 0 if positive else Decimal(value) >= 0
    except InvalidOperation:
        return False


def incomplete_reason(raw, version):
    if version != 3:
        return "NS接口尚未提供明确的行关联，请更新财务核对RESTlet及来源追溯脚本"
    if not raw.get("declarationId") or not re.fullmatch(r"CD[A-Za-z0-9_-]+", raw.get("recordNumber", "")):
        return "报关单来源身份不完整，暂不可整单审核"
    if raw.get("reviewIssues"):
        return "；".join(raw["reviewIssues"])
    customs = [row for row in raw["rows"] if row["side"] == "customs"]
    purchases = [row for row in raw["rows"] if row["side"] == "purchase"]
    if not customs or not purchases:
        return "报关单缺少报关或子采购明细"
    if any(not row.get("sourceKey") for row in raw["rows"]):
        return "NS来源行身份缺失"
    customs_ids = {row["id"] for row in customs}
    if any(row.get("customsRowId") not in customs_ids for row in purchases):
        return "存在未明确归属报关行的采购明细"
    if any(not any(item["customsRowId"] == row["id"] for item in purchases) for row in customs):
        return "部分报关行尚未关联子采购明细"
    for row in raw["rows"]:
        cells = row["cells"]
        required = (0, 2, 8, 9, 12, 16) if row["side"] == "customs" else (5, 7, 9, 12)
        if any(cells[i].strip() in {"", "未填写", "待确认", "—"} for i in required):
            return "报关单或采购明细存在缺失的业务字段，请补齐后重新查询"
        if not number(cells[11], positive=True) or not number(cells[14]):
            return "明细数量或金额缺失／无效，不能审核"
        if row["side"] == "purchase" and not row.get("currency"):
            return "采购币种缺失，不能确认审核金额"
    return ""


def comparison_view(evidence, head):
    comparison = evidence.get("comparison")
    if not comparison or evidence.get("mode") == "evidence_backfill":
        return None
    try:
        payload = comparison["payload"]
        group = ScriptGroup.model_validate(payload["group"])
        customs = [row for row in group.rows if row.side == "customs"]
        purchases = [row for row in group.rows if row.side == "purchase"]
        if (
            payload["version"] != 3
            or group.declarationId != head["ns_internal_id"]
            or group.recordNumber != head["record_no"]
            or any(len(row.cells) != 17 for row in group.rows)
            or len({row.id for row in group.rows}) != len(group.rows)
            or group.customsCount != len(customs)
            or group.purchaseCount != len(purchases)
            or any(row.customsRowId and row.customsRowId not in {c.id for c in customs} for row in purchases)
            or comparison["digest"] != source_digest(payload)
            or comparison["ready"] != (not incomplete_reason(payload["group"], 3))
        ):
            raise ValueError()
        return {key: comparison[key] for key in ("payload", "digest", "ready", "reason")}
    except (KeyError, TypeError, ValueError, ValidationError):
        raise ApiError(503, "已保存的逐行关联契约或身份不一致，请重新同步该报关单") from None
