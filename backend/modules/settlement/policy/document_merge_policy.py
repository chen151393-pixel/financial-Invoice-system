"""资料组合并资格（纯函数）：不按申报抬头限制，只按客户、币种、当前依据与占用校验。"""

from backend.core.names import normalize_name


def original_basis(row, group):
    if group and (
        normalize_name(group["consignee"]) != normalize_name(row["consignee"])
        or group["currency"] != row["currency"]
    ):
        return "原单票组的客户或币种依据已变化，请核对来源"
    return ""


def eligibility(row, group, count):
    if group and count > 1:
        return f"已在多票资料组 {group['group_no']} 中"
    if original_basis(row, group):
        return original_basis(row, group)
    if row["route"] != "direct":
        return "仅直接收汇报关单可以合并资料"
    if row["currency_issue"] or row["amount"] is None or not row["consignee"]:
        return row["currency_issue"] or "报关单的客户、币种或金额依据不完整"
    return ""


def checks(source, numbers, requested_count, rows, occupied, counts, shared_valid):
    found = len(rows) == len(numbers)
    usable = found and all(
        not eligibility(r, None, 0) and not original_basis(r, occupied.get(r["declaration_no"])) for r in rows
    )
    same_buyer = bool(rows) and all(
        normalize_name(r["consignee"]) == normalize_name(source["consignee"]) for r in rows
    )
    same_currency = bool(rows) and all(r["currency"] == source["currency"] for r in rows)
    free = all(counts.get(g["id"], 0) <= 1 for g in occupied.values())
    return [
        dict(key="count", label="至少两票", passed=len(numbers) >= 2, detail=f"已选 {len(numbers)} 票"),
        dict(
            key="source",
            label="包含本单且不重复",
            passed=source["declaration_no"] in numbers and requested_count == len(numbers),
            detail=source["declaration_no"],
        ),
        dict(key="customer", label="同一境外收货人", passed=same_buyer, detail=source["consignee"]),
        dict(key="currency", label="同一币种", passed=same_currency, detail=source["currency"]),
        dict(
            key="available",
            label="都不在其他多票资料组",
            passed=free,
            detail="可合并单票组；已有多票组不能重复选入",
        ),
        dict(key="basis", label="当前报关依据有效", passed=usable, detail="已关联 NS 的当前直接收汇海关回执"),
        dict(
            key="bill",
            label="共用提单归属正确",
            passed=shared_valid,
            detail="使用本单提单，或合并后上传、核对",
        ),
    ]
