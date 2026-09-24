"""关系证据与独立结果表的纯转换；不查询数据库或调用NS。"""

from datetime import UTC, datetime

from backend.core.errors import ApiError

from .relation_policy import comparison_view

META_FIELDS = {"version", "account", "declarationId", "readAt", "status", "mode", "issues", "comparison"}


def instant(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(UTC).replace(tzinfo=None)
    except (ValueError, AttributeError):
        raise ApiError(502, "关联来源时间格式无效，未保存") from None


def relation_values(head, evidence):
    evidence = evidence or {
        "version": 1,
        "account": head["ns_account"],
        "declarationId": head["ns_internal_id"],
        "status": "partial",
        "issues": ["本次单据快照未包含逐行关联依据，请完整同步。"],
    }
    if (
        evidence.get("version") != 1
        or evidence.get("account") != head["ns_account"]
        or evidence.get("declarationId") != head["ns_internal_id"]
        or evidence.get("status") not in {"partial", "collected", "matched"}
    ):
        raise ApiError(502, "关联依据的身份、账套或版本不一致，未保存")
    comparison = comparison_view(evidence, head)
    now = datetime.now(UTC).replace(tzinfo=None)
    return {
        "tenant_id": head["tenant_id"],
        "ns_account": head["ns_account"],
        "customs_declaration_id": head["id"],
        "evidence_version": evidence["version"],
        "status": evidence["status"],
        "mode": evidence.get("mode", "full_sync"),
        "review_ready": bool(comparison and comparison["ready"]),
        "reason": comparison["reason"] if comparison else "；".join(evidence.get("issues", [])),
        "issues": evidence.get("issues", []),
        "raw_line_count": len(evidence.get("rawLines", [])),
        "packing_line_count": len(evidence.get("packingLines", [])),
        "purchase_link_count": len(evidence.get("purchaseLinks", [])),
        "parent_line_count": len(evidence.get("parentLines", [])),
        "evidence_data": {key: value for key, value in evidence.items() if key not in META_FIELDS},
        "evidence_read_at": instant(evidence.get("readAt")),
        "comparison_payload": comparison["payload"] if comparison else None,
        "comparison_digest": comparison["digest"] if comparison else None,
        "query_request_id": evidence.get("comparison", {}).get("requestId") if comparison else None,
        "query_completed_at": instant(evidence.get("comparison", {}).get("readCompletedAt"))
        if comparison
        else None,
        "created_at": now,
        "updated_at": now,
    }


def relation_evidence(row, declaration_id):
    def iso(value):
        return value.replace(tzinfo=UTC).isoformat() if value else None

    evidence = {
        **row.get("evidence_data", {}),
        "version": row["evidence_version"],
        "account": row["ns_account"],
        "declarationId": declaration_id,
        "status": row["status"],
        "mode": row["mode"],
        "issues": row["issues"],
        "readAt": iso(row["evidence_read_at"]),
    }
    if row["comparison_payload"] is not None:
        evidence["comparison"] = {
            "payload": row["comparison_payload"],
            "digest": row["comparison_digest"],
            "ready": bool(row["review_ready"]),
            "reason": row["reason"],
            "requestId": row["query_request_id"],
            "readCompletedAt": iso(row["query_completed_at"]),
        }
    return evidence
