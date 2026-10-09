"""列表摘要只使用匹配评估和已保存关系，不将人工确认解释为税务查验。"""

from collections import Counter
from decimal import Decimal, localcontext


def matching_summary(invoice, candidates, links, allocations, conflicting_clues=False):
    result = {
        "invoiceId": invoice["id"],
        "method": "未关联",
        "confidence": "—",
        "validation": "待匹配",
        "tone": "neutral",
    }
    history = links or allocations
    if history:
        result["method"] = "人工关联" if links else "数量分配"
        if any(row["needsReview"] for row in history):
            return {**result, "confidence": "待复核", "validation": "来源变化，待复核", "tone": "warning"}
        if links:
            differences = any(row["warnings"] for row in links)
            return {
                **result,
                "confidence": "有差异" if differences else "一致",
                "validation": "已确认（有差异）" if differences else "已确认",
                "tone": "warning" if differences else "success",
            }
        with localcontext() as ctx:
            ctx.prec = 64
            quantities = {}
            for row in allocations:
                key = row["invoiceLineId"]
                quantities[key] = quantities.get(key, Decimal(0)) + Decimal(row["quantity"])
            complete = all(
                item.get("quantity") is not None
                and quantities.get(item["id"], Decimal(0)) == Decimal(item["quantity"])
                for item in invoice["lines"]
            )
        return {
            **result,
            "confidence": "已核对",
            "validation": "已确认" if complete else "部分分配",
            "tone": "success",
        }
    if not candidates:
        return result
    matched = [row for row in candidates if row["allFieldsMatched"] and row["allowed"]]
    counts = Counter(row["invoiceLineId"] for row in matched)
    # 逐行覆盖且子采购明细不重复，才展示整票高可信；不能用最高单行结果代表整票。
    covered = bool(invoice["lines"]) and all(counts[item["id"]] for item in invoice["lines"])
    unique = (
        covered
        and all(count == 1 for count in counts.values())
        and len({row["purchaseLineId"] for row in matched}) == len(matched)
    )
    if conflicting_clues or not covered:
        return {**result, "confidence": "有差异", "validation": "待核实", "tone": "warning"}
    if not unique:
        return {**result, "confidence": "待核实", "validation": "多个候选，待确认", "tone": "warning"}
    return {**result, "confidence": "高", "validation": "待确认"}
