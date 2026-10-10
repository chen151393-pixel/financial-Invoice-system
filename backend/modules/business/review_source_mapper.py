"""财务人工审核的本地来源快照；不把匹配完整性当作人工审核结论。"""

from datetime import date, datetime
from decimal import Decimal

from backend.modules.source.public import source_digest


def normalize(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def review_sources(data):
    def document(row):
        # 重复拉取时间不改变审核内容；来源版本、金额、数量、关联和有效状态仍参与摘要。
        return {
            key: value
            for key, value in row.items()
            if key not in {"source_data", "synced_at", "last_complete_sync_at"}
        }

    sources = {}
    for head in data["heads"]:
        purchases = [row for row in data["purchases"] if row["customs_declaration_id"] == head["id"]]
        purchase_ids = {row["id"] for row in purchases}
        relation = data.get("relations", {}).get(head["id"], {}).get("comparison")
        content = normalize(
            {
                "source": "database",
                "version": 1,
                "head": document(head),
                "customsLines": [
                    document(row) for row in data["details"] if row["customs_declaration_id"] == head["id"]
                ],
                "purchases": [document(row) for row in purchases],
                "purchaseLines": [
                    document(row) for row in data["lines"] if row["purchase_order_id"] in purchase_ids
                ],
                "comparison": relation["payload"] if relation else None,
                "lineRelations": data.get("relations", {}).get(head["id"], {}).get("lineRelations", {}),
            }
        )
        sources[head["id"]] = {"content": content, "digest": source_digest(content)}
    return {**data, "review_sources": sources}
