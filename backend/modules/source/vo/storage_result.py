"""来源保存计数与逐单结果汇总；只表达已确认的提交结果。"""

from datetime import datetime, timezone

from ..mapper.admission_filter import skipped_warning


def storage_result(bundle, counts):
    relations = list(bundle.get("relation_evidence", {}).values())
    skipped = skipped_warning(bundle.get("skipped", []))
    partial = sum(value["status"] == "partial" for value in relations)
    return {
        "purchase": counts["purchase"],
        "customs": counts["customs"],
        "relations": {
            "declarations": len(relations),
            "collected": len(relations) - partial,
            "partial": partial,
            "matched": sum(value["status"] == "matched" for value in relations),
            "rawLines": sum(len(value["rawLines"]) for value in relations),
            "packingLines": sum(len(value["packingLines"]) for value in relations),
            "purchaseLinks": sum(len(value["purchaseLinks"]) for value in relations),
        },
        "warnings": list(
            dict.fromkeys(
                ([skipped] if skipped else [])
                + bundle["warnings"]
                + [issue for value in relations for issue in value["issues"]]
            )
        ),
        "skipped": [
            {key: item[key] for key in ("id", "number", "reason")}
            for item in bundle.get("skipped", [])
            if item["kind"] == "customs"
        ],
        "savedAt": datetime.now(timezone.utc).isoformat(),
        "message": (
            "单据及关联结果已保存到MySQL；部分来源存在待核实项"
            if partial
            else "单据、来源依据及逐行关联结果已保存到MySQL"
        )
        if bundle["purchases"] or bundle["customs"]
        else "本页报关单均未出库，已跳过，未保存"
        if skipped
        else "本页没有可保存的单据，已有本地数据保持不变",
    }
