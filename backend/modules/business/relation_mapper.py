"""财务视图只读取已校验的展示契约；原始NS记录和Packing正文留在业务库。"""

from backend.modules.source.public import comparison_view, local_line_relations

from .relation_storage_mapper import relation_evidence


def summarize_relations(data):
    heads, relations = [], {}
    results = {row["customs_declaration_id"]: row for row in data.get("relation_results", [])}
    for row in data["heads"]:
        head = dict(row)
        result = results.get(head["id"])
        evidence = relation_evidence(result, head["ns_internal_id"]) if result is not None else None
        if (
            isinstance(evidence, dict)
            and evidence.get("version") == 1
            and evidence.get("account") == head["ns_account"]
            and evidence.get("declarationId") == head["ns_internal_id"]
            and evidence.get("status") in ("collected", "partial", "matched")
        ):
            relations[head["id"]] = {
                "status": evidence["status"],
                "rawLines": result["raw_line_count"],
                "packingLines": result["packing_line_count"],
                "issues": list(evidence.get("issues", [])),
                "comparison": comparison_view(evidence, head),
                "lineRelations": local_line_relations(
                    head,
                    [item for item in data["details"] if item["customs_declaration_id"] == head["id"]],
                    [item for item in data["purchases"] if item["customs_declaration_id"] == head["id"]],
                    data["lines"],
                    evidence,
                ),
            }
        head.pop("source_data", None)
        heads.append(head)
    return {
        **{key: value for key, value in data.items() if key != "relation_results"},
        "heads": heads,
        "purchases": [
            {key: value for key, value in row.items() if key != "source_data"} for row in data["purchases"]
        ],
        "relations": relations,
    }
